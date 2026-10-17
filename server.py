import asyncio
import html as html_lib
import json
import os
import re
import shutil
import sqlite3
import urllib.request
from datetime import datetime
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.base import BaseHTTPMiddleware

app = FastAPI(title="PillScamRadar API & SSR Engine", version="2.0")
app.add_middleware(GZipMiddleware, minimum_size=1000)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class SmartCacheMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        path = request.url.path.lower()
        if path.startswith("/admin"):
            response.headers["Cache-Control"] = "no-store"
        elif any(path.endswith(ext) for ext in (".css", ".js", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico", ".woff2", ".ttf")) or path.startswith("/static/") or path.startswith("/uploads/"):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        elif path in ("/robots.txt", "/llms.txt", "/.well-known/llms.txt") or path.endswith(".xml"):
            response.headers["Cache-Control"] = "public, max-age=3600, s-maxage=86400"
        elif request.method in ("GET", "HEAD") and response.status_code == 200:
            response.headers["Cache-Control"] = "public, max-age=300, s-maxage=3600, stale-while-revalidate=86400"
        return response


app.add_middleware(SmartCacheMiddleware)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCAL_DB_PATH = os.path.join(BASE_DIR, "scams.db")

if os.path.exists("/var/data"):
    PERSISTENT_DIR = "/var/data"
    DB_PATH = os.path.join(PERSISTENT_DIR, "scams.db")
else:
    PERSISTENT_DIR = BASE_DIR
    DB_PATH = LOCAL_DB_PATH


def get_row_count(db_file: str) -> int:
    if not os.path.exists(db_file):
        return -1
    try:
        conn = sqlite3.connect(db_file, timeout=10.0)
        cnt = conn.execute("SELECT COUNT(*) FROM regulatory_scam_reports").fetchone()[0]
        conn.close()
        return cnt
    except Exception:
        return -1


def sync_git_db_to_persistent(force: bool = False):
    if DB_PATH == LOCAL_DB_PATH or not os.path.exists(LOCAL_DB_PATH):
        return
    local_cnt = get_row_count(LOCAL_DB_PATH)
    pers_cnt = get_row_count(DB_PATH)
    if force or pers_cnt < local_cnt:
        print(f"[DB Sync] Replacing {DB_PATH} ({pers_cnt} rows) with {LOCAL_DB_PATH} ({local_cnt} rows)...")
        for suffix in ("", "-wal", "-shm"):
            p = DB_PATH + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        shutil.copy2(LOCAL_DB_PATH, DB_PATH)
        print(f"[DB Sync] Successfully synced {get_row_count(DB_PATH)} rows to {DB_PATH}!")


sync_git_db_to_persistent()

if os.path.exists("uploads"):
    app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


def get_db_connection(timeout: float = 30.0):
    conn = sqlite3.connect(DB_PATH, timeout=timeout)
    conn.execute("PRAGMA busy_timeout = 30000;")
    conn.execute("PRAGMA synchronous = NORMAL;")
    conn.execute("PRAGMA temp_store = MEMORY;")
    return conn


PRIORITY_ORDER_SQL = """
    CASE
        WHEN scam_type IN ('Unapproved/Tainted Drug', 'Tainted Male Enhancement', 'Tainted Weight Loss Pill', 'Tainted Product', 'Dietary Supplement', 'WHO Falsified Medical Product Alert') THEN 0
        WHEN scam_type IN ('Unapproved Drug', 'MHRA Safety Alert', 'MHRA Drug/Device Recall', 'Falsified/Fake Medicine') THEN 1
        ELSE 2
    END,
    discovered_date DESC,
    id DESC
"""

FOOTER_HTML = """
    <footer class="vasiledev-ecosystem-footer" style="background: #03060a; border-top: 1px solid rgba(255, 255, 255, 0.1); padding: 50px 20px 24px; font-family: 'Inter', system-ui, -apple-system, sans-serif; color: #94a3b8; font-size: 0.85rem; line-height: 1.6; text-align: left; margin-top: 60px;">
        <div style="max-width: 1180px; margin: 0 auto; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 36px; margin-bottom: 36px;">
            <div>
                <div style="display: flex; align-items: center; gap: 10px; margin-bottom: 12px;">
                    <span style="display: inline-flex; align-items: center; justify-content: center; width: 34px; height: 34px; border-radius: 8px; background: rgba(16, 185, 129, 0.15); color: #10b981; font-size: 16px;">
                        <i class="fa-solid fa-pills"></i>
                    </span>
                    <span style="font-size: 18px; font-weight: 800; color: #ffffff; letter-spacing: -0.3px;">
                        PILLSCAM<strong style="color: #10b981;">RADAR</strong>
                    </span>
                </div>
                <p style="color: #94a3b8; font-size: 0.85rem; line-height: 1.5; margin: 0 0 12px 0;">
                    Healthcare intelligence platform. Indexing official FDA, MHRA, and WHO recalls of tainted supplements, counterfeit pharmaceuticals, and dangerous weight-loss &amp; enhancement pills.
                </p>
                <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                    <span style="background: rgba(16, 185, 129, 0.12); color: #10b981; border: 1px solid rgba(16, 185, 129, 0.3); font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px;">✔️ VIES Verified EU</span>
                    <span style="background: rgba(56, 189, 248, 0.12); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.3); font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 6px;">🛡️ 100% Free Public Utility</span>
                </div>
            </div>
            <div>
                <h4 style="font-size: 1rem; font-weight: 700; color: #38bdf8; margin: 0 0 14px 0;">VasileDev Group Ecosystem</h4>
                <p style="margin: 0 0 8px 0; color: #ffffff; font-weight: 600; font-size: 0.85rem;">VasileDev Group</p>
                <p style="margin: 0 0 8px 0; color: #cbd5e1; font-size: 0.85rem;">VAT / P.IVA: <code style="background: rgba(255, 255, 255, 0.1); color: #38bdf8; padding: 2px 6px; border-radius: 4px; font-family: monospace;">IT04226190041</code></p>
                <p style="margin: 0 0 8px 0; color: #94a3b8; font-size: 0.85rem;">Locations: Garessio (CN), Italy &amp; Odobești, Romania</p>
                <p style="margin: 0 0 8px 0; color: #94a3b8; font-size: 0.85rem;">Direct: <a href="mailto:amendamax@vasiledev.com" style="color: #cbd5e1; text-decoration: none;">amendamax@vasiledev.com</a></p>
                <p style="margin: 0; color: #94a3b8; font-size: 0.85rem;">WhatsApp: <strong style="color: #cbd5e1;">+39 320 948 1876</strong></p>
            </div>
            <div>
                <h4 style="font-size: 1rem; font-weight: 700; color: #38bdf8; margin: 0 0 14px 0;">Official Network</h4>
                <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px 16px; font-size: 0.85rem;">
                    <a href="https://isbrokersafe.com" target="_blank" rel="noopener" style="color: #cbd5e1; text-decoration: none; white-space: nowrap;">🏛️ IsBrokerSafe.com</a>
                    <a href="https://verifydating.net" target="_blank" rel="noopener" style="color: #cbd5e1; text-decoration: none; white-space: nowrap;">🛡️ VerifyDating.net</a>
                    <a href="https://dreamcarhunt.com" target="_blank" rel="noopener" style="color: #cbd5e1; text-decoration: none; white-space: nowrap;">🏎️ DreamCarHunt.com</a>
                    <a href="https://airparkrefund.com" target="_blank" rel="noopener" style="color: #cbd5e1; text-decoration: none; white-space: nowrap;">✈️ AirParkRefund.com</a>
                    <a href="https://jobscamradar.com" target="_blank" rel="noopener" style="color: #cbd5e1; text-decoration: none; white-space: nowrap;">💼 JobScamRadar.com</a>
                    <a href="https://pillscamradar.com" style="color: #10b981; font-weight: 700; text-decoration: none; white-space: nowrap;">💊 PillScamRadar.com</a>
                    <a href="https://appscamradar.com" target="_blank" rel="noopener" style="color: #cbd5e1; text-decoration: none; white-space: nowrap;">📱 AppScamRadar.com</a>
                    <a href="https://calcolaincentivi.it" target="_blank" rel="noopener" style="color: #cbd5e1; text-decoration: none; white-space: nowrap;">⚡ CalcolaIncentivi.it</a>
                    <a href="https://vasiledev.com" target="_blank" rel="noopener" style="color: #cbd5e1; text-decoration: none; white-space: nowrap;">👑 VasileDev.com</a>
                </div>
            </div>
        </div>
        <div style="max-width: 1180px; margin: 0 auto; border-top: 1px solid rgba(255, 255, 255, 0.05); padding-top: 20px; text-align: center; font-size: 0.8rem; color: #64748b;">
            <p style="margin: 0;">&copy; 2026 PillScamRadar™ by VasileDev Group (P.IVA IT04226190041). All Rights Reserved. Intellectual Property Protected under EU Copyright Law.</p>
            <div style="text-align: center; margin-top: 14px; display: flex; justify-content: center; gap: 18px; flex-wrap: wrap;">
                <a href="/directory/pills/1" style="color: #38bdf8; text-decoration: none; font-weight: 600;">&bull; Browse Full FDA &amp; MHRA Recall Directory</a>
                <a href="/privacy" style="color: #94a3b8; text-decoration: none;">Privacy Policy &amp; GDPR</a>
                <a href="/sitemap.xml" style="color: #94a3b8; text-decoration: none;">XML Sitemap</a>
                <a href="/llms.txt" style="color: #94a3b8; text-decoration: none;">LLMs.txt</a>
            </div>
        </div>
    </footer>
"""


def render_table_row(slug, entity_name, domain_url, scam_type, severity_level, status, description, discovered_date):
    badge_class = (severity_level or "high").lower()
    if badge_class not in ("critical", "high", "medium", "low"):
        badge_class = "high"
    short_desc = (description or "")[:240]
    if len(description or "") > 240:
        short_desc += "..."
    return f"""
        <tr>
            <td style="white-space: nowrap; color: #94a3b8; font-size: 0.9rem;">{html_lib.escape(str(discovered_date or ''))}</td>
            <td><a href="/scam/{html_lib.escape(str(slug))}" style="text-decoration: none;"><span class="firm-name">{html_lib.escape(str(entity_name or ''))}</span></a><br><small style="color: #94a3b8;">{html_lib.escape(str(domain_url or ''))}</small></td>
            <td class="description"><strong style="color: #f8fafc;">{html_lib.escape(str(scam_type or ''))}</strong><br>{html_lib.escape(short_desc)}</td>
            <td><span class="badge {badge_class}">{html_lib.escape(str(severity_level or 'HIGH'))}</span></td>
            <td><strong style="color: #f87171; font-size: 0.85rem;">{html_lib.escape(str(status or 'RECALLED'))}</strong></td>
        </tr>"""


@app.on_event("startup")
async def startup_event():
    sync_git_db_to_persistent()
    asyncio.create_task(daily_harvester_loop())


async def daily_harvester_loop():
    await asyncio.sleep(60)
    while True:
        try:
            import fda_harvester
            import mhra_harvester
            fda_harvester.fetch_fda_alerts()
            mhra_harvester.fetch_mhra_alerts()
        except Exception as e:
            print(f"[Daily Harvester Error]: {e}")
        await asyncio.sleep(86400)


@app.get("/admin/force-sync-db")
async def force_sync_db(secret: str):
    if secret != "vasile2026":
        return JSONResponse({"error": "Unauthorized"}, status_code=403)
    try:
        url = "https://raw.githubusercontent.com/amendamax/pill-scam-radar/main/scams.db"
        tmp_path = DB_PATH + ".tmp"
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(tmp_path, "wb") as out_f:
            shutil.copyfileobj(resp, out_f)

        for suffix in ("", "-wal", "-shm"):
            p = DB_PATH + suffix
            if os.path.exists(p):
                try:
                    os.remove(p)
                except Exception:
                    pass
        shutil.move(tmp_path, DB_PATH)
        cnt = get_row_count(DB_PATH)
        return JSONResponse({"status": "Success", "total_records": cnt, "db_path": DB_PATH})
    except Exception as e:
        return JSONResponse({"status": "Error", "message": str(e)}, status_code=500)


@app.get("/healthz")
@app.get("/health")
async def health_check():
    cnt = get_row_count(DB_PATH)
    return JSONResponse({"status": "HEALTHY", "total_recalls": cnt, "timestamp": datetime.now().isoformat()})


@app.get("/", response_class=HTMLResponse)
@app.head("/")
async def get_index():
    conn = get_db_connection()
    c = conn.cursor()
    c.execute(f"""
        SELECT slug, entity_name, domain_url, scam_type, severity_level, status, description, discovered_date
        FROM regulatory_scam_reports
        ORDER BY {PRIORITY_ORDER_SQL}
        LIMIT 50
    """)
    rows = c.fetchall()
    total = c.execute("SELECT COUNT(*) FROM regulatory_scam_reports").fetchone()[0]
    conn.close()

    rows_html = "\n".join(render_table_row(*r) for r in rows)
    with open("index.html", "r", encoding="utf-8") as f:
        html = f.read()
    html = html.replace("{initial_rows}", rows_html).replace("{total_recalls}", f"{total:,}")
    return HTMLResponse(content=html)


@app.get("/favicon.svg")
@app.get("/favicon.ico")
async def get_favicon():
    if os.path.exists("favicon.svg"):
        return FileResponse("favicon.svg", media_type="image/svg+xml")
    raise HTTPException(status_code=404)


@app.get("/d89b14f6824945e4a81b7e4521798361.txt", response_class=PlainTextResponse)
async def get_indexnow_key():
    return "d89b14f6824945e4a81b7e4521798361"


@app.get("/robots.txt", response_class=PlainTextResponse)
async def get_robots():
    return """User-agent: *
Allow: /
Disallow: /admin
Disallow: /admin/

# AI Crawlers
User-agent: Google-Extended
Allow: /
User-agent: GPTBot
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Claude-Web
Allow: /

Sitemap: https://pillscamradar.com/sitemap.xml
"""


@app.get("/llms.txt", response_class=PlainTextResponse)
@app.get("/.well-known/llms.txt", response_class=PlainTextResponse)
async def serve_llms_txt():
    return """# PillScamRadar.com — Official FDA, MHRA & WHO Tainted Supplements & Drug Recalls Database
> Operated by VasileDev Group (EU VIES VAT: IT04226190041)

## Overview
PillScamRadar indexes 20,600+ official regulatory enforcement actions, Class I/II/III pharmaceutical recalls, tainted weight-loss and male enhancement supplements (undeclared sildenafil, tadalafil, sibutramine, diclofenac), and WHO falsified medical product alerts.

## Key Endpoints
- Homepage & Live Search: https://pillscamradar.com/
- Paginated Recall Directory: https://pillscamradar.com/directory/pills/1
- Public JSON Search API: https://pillscamradar.com/api/v1/pills?search={query}
- XML Sitemap: https://pillscamradar.com/sitemap.xml
"""


@app.get("/privacy", response_class=HTMLResponse)
@app.get("/privacy-policy", response_class=HTMLResponse)
@app.get("/privacy-policy.html", response_class=HTMLResponse)
@app.get("/terms.html", response_class=HTMLResponse)
async def serve_privacy():
    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Privacy Policy, GDPR &amp; Medical Disclaimer | PillScamRadar</title>
        <meta name="description" content="Privacy Policy, GDPR compliance, and medical regulatory disclaimer for PillScamRadar.com by VasileDev Group (P.IVA IT04226190041).">
        <link rel="canonical" href="https://pillscamradar.com/privacy">
        <link rel="icon" type="image/svg+xml" href="/favicon.svg">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            body {{ background-color: #020617; color: #f8fafc; font-family: system-ui, -apple-system, sans-serif; margin: 0; padding: 40px 20px 0; line-height: 1.65; }}
            .container {{ max-width: 860px; margin: 0 auto; background: rgba(15, 23, 42, 0.85); padding: 40px; border-radius: 16px; border: 1px solid rgba(255, 255, 255, 0.1); }}
            a {{ color: #38bdf8; text-decoration: none; }}
            p {{ color: #cbd5e1; }}
        </style>
    </head>
    <body>
        <div class="container">
            <p><a href="/">&larr; Back to PillScamRadar</a></p>
            <h1>Privacy Policy, GDPR &amp; Regulatory Disclaimer</h1>
            <p><strong>PillScamRadar.com</strong> is a public healthcare regulatory intelligence platform operated by <strong>VasileDev Group (Bratu Vasile)</strong>, registered in the European Union under VAT / P.IVA <code>IT04226190041</code> (VIES Verified), with operational offices in Garessio (CN), Italy and Odobești, Romania.</p>
            <h3>1. Information Sources &amp; Medical Disclaimer</h3>
            <p>All recall, enforcement, and laboratory analysis records are aggregated from official public health repositories including the U.S. Food and Drug Administration (OpenFDA), the UK Medicines and Healthcare products Regulatory Agency (MHRA), and the World Health Organization (WHO). Information on PillScamRadar is for educational and public safety verification purposes only and does not constitute medical advice.</p>
            <h3>2. GDPR &amp; Data Protection (EU Reg. 2016/679)</h3>
            <p>Search queries on PillScamRadar are processed anonymously without storing personal health profiles. For inquiries or data requests, contact <a href="mailto:amendamax@vasiledev.com">amendamax@vasiledev.com</a>.</p>
            <h3>3. Affiliate Disclosure</h3>
            <p>To keep this database 100% free for public access, pages include clearly labeled sponsored partner links (<code>rel="sponsored"</code>) to verified supplement and optical care providers.</p>
        </div>
        {FOOTER_HTML}
    </body>
    </html>"""
    return HTMLResponse(content=html)


@app.get("/scammers")
@app.get("/pills")
@app.get("/directory")
async def redirect_directory():
    return RedirectResponse(url="/directory/pills/1", status_code=301)


@app.get("/scam/{slug}", response_class=HTMLResponse)
@app.get("/report/{slug}", response_class=HTMLResponse)
async def get_pill_scam_page(slug: str):
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date
        FROM regulatory_scam_reports WHERE slug = ?
    """, (slug,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return HTMLResponse("<h1>404 Not Found</h1>", status_code=404)

    safe_name = html_lib.escape(str(row[0] or "Unknown Product"))
    safe_id = html_lib.escape(str(row[1] or "Official Alert"))
    safe_type = html_lib.escape(str(row[2] or "Drug Recall"))
    safe_sev = html_lib.escape(str(row[3] or "HIGH"))
    safe_status = html_lib.escape(str(row[4] or "RECALLED"))
    safe_reg = html_lib.escape(str(row[5] or "FDA / MHRA"))
    safe_desc = html_lib.escape(str(row[6] or ""))
    safe_date = html_lib.escape(str(row[7] or "2026-01-01"))
    meta_desc = html_lib.escape(f"Official {row[2]} Alert for {row[0]} ({row[1]}): {str(row[6] or '')[:140]}...")

    schema_ld = {
        "@context": "https://schema.org",
        "@type": "MedicalWebPage",
        "headline": f"Regulatory Alert: {row[0]} — {row[2]}",
        "description": str(row[6] or "")[:300],
        "datePublished": str(row[7] or "2026-01-01"),
        "url": f"https://pillscamradar.com/scam/{slug}",
        "publisher": {
            "@type": "Organization",
            "name": "PillScamRadar by VasileDev Group",
            "vatID": "IT04226190041",
            "url": "https://pillscamradar.com",
        },
    }

    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FDA/MHRA Recall Alert: {safe_name} ({safe_type}) | PillScamRadar</title>
        <meta name="description" content="{meta_desc}">
        <link rel="canonical" href="https://pillscamradar.com/scam/{html_lib.escape(slug)}">
        <link rel="icon" type="image/svg+xml" href="/favicon.svg">
        <meta property="og:type" content="article">
        <meta property="og:title" content="FDA/MHRA Alert: {safe_name} — {safe_type}">
        <meta property="og:description" content="{meta_desc}">
        <meta property="og:url" content="https://pillscamradar.com/scam/{html_lib.escape(slug)}">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <script type="application/ld+json">{json.dumps(schema_ld)}</script>
        <style>
            body {{ font-family: system-ui, -apple-system, sans-serif; background: linear-gradient(to bottom, rgba(2,6,23,0.55), rgba(2,6,23,0.82)), url('/uploads/pill_bg.jpg?v=5') center top / cover fixed; color: #f8fafc; margin: 0; padding: 0; line-height: 1.6; }}
            header {{ background-color: rgba(15,23,42,0.9); padding: 20px; text-align: center; border-bottom: 1px solid #1e293b; }}
            header h1 {{ margin: 0; font-size: 28px; color: #38bdf8; }}
            header a {{ color: #38bdf8; text-decoration: none; }}
            .container {{ max-width: 1000px; margin: 40px auto; padding: 0 20px; }}
            .dossier {{ background: rgba(15,23,42,0.9); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; padding: 30px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }}
            .header-dossier {{ border-bottom: 1px solid rgba(255,255,255,0.1); padding-bottom: 20px; margin-bottom: 20px; }}
            .header-dossier h1 {{ margin: 0 0 10px 0; font-size: 30px; color: #f8fafc; }}
            .badge {{ display: inline-block; font-size: 13px; font-weight: 800; padding: 5px 12px; border-radius: 6px; margin-bottom: 10px; color: white; background-color: #ef4444; text-transform: uppercase; }}
            .badge.high {{ background-color: #f59e0b; color: #020617; }}
            .badge.medium {{ background-color: #3b82f6; }}
            .details-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }}
            .detail-item {{ background: rgba(255,255,255,0.05); padding: 15px; border-radius: 8px; border: 1px solid rgba(255,255,255,0.05); word-break: break-word; }}
            .detail-item strong {{ color: #94a3b8; display: block; font-size: 12px; text-transform: uppercase; margin-bottom: 5px; }}
            .reason {{ margin-top: 30px; padding: 20px; background: rgba(239, 68, 68, 0.1); border-left: 4px solid #ef4444; border-radius: 0 8px 8px 0; }}
            .reason h3 {{ margin-top: 0; color: #ef4444; }}
            .back-link {{ display: inline-block; margin-bottom: 20px; color: #38bdf8; text-decoration: none; font-weight: 600; }}
            .back-link:hover {{ text-decoration: underline; }}
            .affiliate-section {{ margin-top: 36px; display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }}
            .aff-card {{ padding: 25px; border-radius: 12px; text-align: center; border: 1px solid rgba(255,255,255,0.12); display: flex; flex-direction: column; justify-content: space-between; }}
            .aff-card.health {{ background: rgba(2, 44, 34, 0.9); border-color: rgba(16, 185, 129, 0.4); }}
            .aff-card.vision {{ background: rgba(15, 23, 42, 0.92); border-color: rgba(56, 189, 248, 0.4); }}
            .aff-card h4 {{ margin: 0 0 12px 0; font-size: 20px; color: #f8fafc; }}
            .aff-card p {{ font-size: 14.5px; color: #cbd5e1; margin: 0 0 18px 0; }}
            .aff-card a {{ display: inline-block; padding: 12px 22px; border-radius: 8px; text-decoration: none; font-weight: 800; color: #020617; background: #10b981; }}
            .aff-card.vision a {{ background: #38bdf8; }}
            @media (max-width: 600px) {{ .details-grid {{ grid-template-columns: 1fr; }} }}
        </style>
        <!-- Google tag (gtag.js) -->
        <script async src="https://www.googletagmanager.com/gtag/js?id=G-JYVX5B6FRC"></script>
        <script>
          window.dataLayer = window.dataLayer || [];
          function gtag(){{dataLayer.push(arguments);}}
          gtag('js', new Date());
          gtag('config', 'G-JYVX5B6FRC');
        </script>
    </head>
    <body>
        <header>
            <h1><a href="/"><i class="fa-solid fa-capsules" style="color: #10b981;"></i> PILLSCAM<span style="color: #10b981;">RADAR</span></a></h1>
        </header>
        <div class="container">
            <a href="/" class="back-link">&larr; Back to FDA &amp; MHRA Recall Database</a>

            <div class="dossier">
                <div class="header-dossier">
                    <div class="badge {safe_sev.lower()}">{safe_sev} RISK ALERT</div>
                    <h1>{safe_name}</h1>
                </div>

                <div class="details-grid">
                    <div class="detail-item"><strong>Recall / Reference ID</strong> {safe_id}</div>
                    <div class="detail-item"><strong>Regulatory Status</strong> <span style="color: #ef4444; font-weight: bold;">{safe_status}</span></div>
                    <div class="detail-item"><strong>Violation Classification</strong> {safe_type}</div>
                    <div class="detail-item"><strong>Date Logged</strong> {safe_date}</div>
                    <div class="detail-item" style="grid-column: 1 / -1;"><strong>Affected Lots / Regulatory Authority</strong> {safe_reg}</div>
                </div>

                <div class="reason">
                    <h3>Official Laboratory &amp; Enforcement Findings</h3>
                    <p style="margin: 0; line-height: 1.65;">{safe_desc}</p>
                </div>
            </div>

            <div class="affiliate-section">
                <div class="aff-card health">
                    <div>
                        <h4>🌿 Looking for Safe, Lab-Tested Alternatives?</h4>
                        <p>Stop risking your health with unapproved or tainted pills. Discover 100% FDA-compliant, third-party tested dietary supplements.</p>
                    </div>
                    <a href="https://health-beauty-healthbuy.myshopify.com?bg_ref=giNiA8PB3v" target="_blank" rel="sponsored noopener noreferrer">View Verified Safe Supplements &rarr;</a>
                </div>

                <div class="aff-card vision">
                    <div>
                        <h4 style="color: #38bdf8;">👓 Certified Vision &amp; Optical Care</h4>
                        <p>Protect your eyes with high-quality, FDA-registered prescription eyewear and blue-light lenses from our verified partner, Fytoo.</p>
                    </div>
                    <a href="https://www.kqzyfj.com/click-101863908-17219119" target="_blank" rel="sponsored noopener noreferrer">Shop Certified Fytoo Eyewear &rarr;</a>
                </div>
            </div>
            <p style="text-align: center; font-size: 12px; color: #64748b; margin-top: 12px;">Disclosure: Sponsored partner links help keep this regulatory database free to the public.</p>
        </div>
        {FOOTER_HTML}
    </body>
    </html>"""
    return HTMLResponse(html)


@app.get("/directory/pills/{page}", response_class=HTMLResponse)
async def get_pill_directory_page(page: int):
    per_page = 100
    if page < 1:
        page = 1
    offset = (page - 1) * per_page
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM regulatory_scam_reports")
    total_count = cursor.fetchone()[0]
    total_pages = max(1, (total_count + per_page - 1) // per_page)
    if page > total_pages:
        page = total_pages
        offset = (page - 1) * per_page

    cursor.execute(f"""
        SELECT slug, entity_name, domain_url, scam_type, severity_level, discovered_date
        FROM regulatory_scam_reports
        ORDER BY {PRIORITY_ORDER_SQL}
        LIMIT ? OFFSET ?
    """, (per_page, offset))
    rows = cursor.fetchall()
    conn.close()

    items_html = ""
    for r in rows:
        items_html += f"""
        <div style="background: rgba(15,23,42,0.9); border: 1px solid #1e293b; border-radius: 8px; padding: 18px 20px; margin-bottom: 14px;">
            <a href="/scam/{html_lib.escape(str(r[0]))}" style="color: #38bdf8; text-decoration: none; font-size: 18px; font-weight: bold;">{html_lib.escape(str(r[1]))}</a>
            <p style="color: #94a3b8; font-size: 14px; margin: 6px 0 0;">ID: {html_lib.escape(str(r[2]))} | Type: {html_lib.escape(str(r[3]))} | Risk: <strong style="color:#f87171;">{html_lib.escape(str(r[4]))}</strong> | Date: {html_lib.escape(str(r[5]))}</p>
        </div>"""

    prev_link = f'<a href="/directory/pills/{page-1}" style="color: #10b981; margin-right: 20px; font-weight: 700; text-decoration: none;">&larr; Previous Page</a>' if page > 1 else ""
    next_link = f'<a href="/directory/pills/{page+1}" style="color: #10b981; font-weight: 700; text-decoration: none;">Next Page &rarr;</a>' if page < total_pages else ""

    html = f"""<!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>FDA &amp; MHRA Tainted Supplement &amp; Drug Recall Directory — Page {page} of {total_pages} | PillScamRadar</title>
        <meta name="description" content="Page {page} of {total_pages} in the PillScamRadar regulatory recall directory ({total_count:,} verified FDA, MHRA, and WHO alerts).">
        <link rel="canonical" href="https://pillscamradar.com/directory/pills/{page}">
        <link rel="icon" type="image/svg+xml" href="/favicon.svg">
        <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
        <style>
            body {{ font-family: system-ui, -apple-system, sans-serif; background: linear-gradient(to bottom, rgba(2,6,23,0.55), rgba(2,6,23,0.82)), url('/uploads/pill_bg.jpg?v=5') center top / cover fixed; color: #f8fafc; margin: 0; padding: 0; }}
            header {{ background-color: rgba(15,23,42,0.9); padding: 20px; text-align: center; border-bottom: 1px solid #1e293b; }}
            header h1 {{ margin: 0; font-size: 28px; color: #38bdf8; }}
            header a {{ color: #38bdf8; text-decoration: none; }}
            .container {{ max-width: 1000px; margin: 40px auto; padding: 0 20px; }}
        </style>
    </head>
    <body>
        <header>
            <h1><a href="/">PILLSCAM<span style="color: #10b981;">RADAR</span></a></h1>
            <p style="color: #94a3b8; margin: 8px 0 0;">Official FDA, MHRA &amp; WHO Recall Directory — Page {page} of {total_pages} ({total_count:,} Total Alerts)</p>
        </header>
        <div class="container">
            {items_html}
            <div style="margin-top: 30px; text-align: center;">
                {prev_link}
                {next_link}
            </div>
        </div>
        {FOOTER_HTML}
    </body>
    </html>"""
    return HTMLResponse(html)


@app.get("/api/v1/pills")
async def api_v1_pills(search: str = "", limit: int = 50, offset: int = 0):
    limit = min(200, max(1, limit))
    offset = max(0, offset)
    conn = get_db_connection()
    cursor = conn.cursor()

    if search:
        search_term = f"%{search}%"
        cursor.execute(f"""
            SELECT slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated
            FROM regulatory_scam_reports
            WHERE entity_name LIKE ? OR description LIKE ? OR domain_url LIKE ? OR scam_type LIKE ?
            ORDER BY {PRIORITY_ORDER_SQL}
            LIMIT ? OFFSET ?
        """, (search_term, search_term, search_term, search_term, limit, offset))
        rows = cursor.fetchall()
        cursor.execute("""
            SELECT COUNT(*) FROM regulatory_scam_reports
            WHERE entity_name LIKE ? OR description LIKE ? OR domain_url LIKE ? OR scam_type LIKE ?
        """, (search_term, search_term, search_term, search_term))
        total = cursor.fetchone()[0]
    else:
        cursor.execute(f"""
            SELECT slug, entity_name, domain_url, scam_type, severity_level, status, regulator_warnings, description, discovered_date, last_updated
            FROM regulatory_scam_reports
            ORDER BY {PRIORITY_ORDER_SQL}
            LIMIT ? OFFSET ?
        """, (limit, offset))
        rows = cursor.fetchall()
        cursor.execute("SELECT COUNT(*) FROM regulatory_scam_reports")
        total = cursor.fetchone()[0]
    conn.close()

    results = []
    for r in rows:
        results.append({
            "slug": r[0],
            "entity_name": r[1],
            "domain_url": r[2],
            "scam_type": r[3],
            "severity_level": r[4],
            "status": r[5],
            "regulator_warnings": r[6],
            "description": r[7],
            "discovered_date": r[8],
            "last_updated": r[9],
        })
    return {"total": total, "results": results}


@app.get("/sitemap.xml")
async def get_pill_sitemap():
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT COUNT(*) FROM regulatory_scam_reports")
    total_count = cursor.fetchone()[0]
    cursor.execute(f"SELECT slug, discovered_date FROM regulatory_scam_reports ORDER BY {PRIORITY_ORDER_SQL}")
    rows = cursor.fetchall()
    conn.close()

    today = datetime.now().strftime("%Y-%m-%d")
    total_dir_pages = max(1, (total_count + 99) // 100)

    urls = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
        f'  <url><loc>https://pillscamradar.com/</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>1.0</priority></url>',
        f'  <url><loc>https://pillscamradar.com/privacy</loc><lastmod>{today}</lastmod><changefreq>monthly</changefreq><priority>0.5</priority></url>',
    ]
    for p in range(1, total_dir_pages + 1):
        urls.append(f'  <url><loc>https://pillscamradar.com/directory/pills/{p}</loc><lastmod>{today}</lastmod><changefreq>daily</changefreq><priority>0.85</priority></url>')

    for slug, disc_date in rows:
        safe_slug = html_lib.escape(str(slug))
        urls.append(f'  <url><loc>https://pillscamradar.com/scam/{safe_slug}</loc><changefreq>monthly</changefreq><priority>0.8</priority></url>')

    urls.append("</urlset>")
    return Response(content="\n".join(urls), media_type="application/xml")


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=10000)

from flask import Flask, request, send_file
import os
import tempfile

from ramadan_calendar_to_pdf import run_calendar

app = Flask(__name__)

ALLOWED_DST = {"LOCK", "DST"}

@app.post("/generate")
def generate():
    zip_code = (request.form.get("zip") or "").strip()
    timezone = (request.form.get("timezone") or "").strip()
    dst = (request.form.get("dst") or "LOCK").strip().upper()

    if not (len(zip_code) == 5 and zip_code.isdigit()):
        return "Invalid ZIP (must be 5 digits).", 400

    if dst not in ALLOWED_DST:
        return "Invalid DST option.", 400

    out_path = None
    try:
        # Generate into temp folder
        out_path = run_calendar(
            zip_code=zip_code,
            timezone=timezone,
            dst_policy=dst,
            out_dir=tempfile.gettempdir(),
        )

        download_name = f"2026_Ramadan_{zip_code}.pdf"

        return send_file(
            out_path,
            mimetype="application/pdf",
            as_attachment=True,
            download_name=download_name,
            conditional=False,
        )
    except Exception as e:
        return f"{type(e).__name__}: {e}", 500
    finally:
        if out_path and os.path.exists(out_path):
            try:
                os.remove(out_path)
            except OSError:
                pass

@app.get("/")
def health():
    return "OK", 200

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)


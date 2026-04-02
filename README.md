# 📄 Ramadan PDF API

A simple Python API that generates **Ramadan calendars as PDF files** using a predefined template.  
Designed for mosques, communities, and developers who want to automate Ramadan schedule creation.

---

## 🚀 Features

- 📅 Generate Ramadan calendars as PDFs  
- 🕌 Supports prayer schedule formatting  
- 🎨 Uses a custom PDF template  
- 🔤 Arabic font support (`Janna LT Bold`)  
- ⚡ Lightweight and fast  
- ☁️ Ready for deployment (Heroku-compatible)

---

## 🛠️ Tech Stack

- **Python**
- **Flask** (API server)
- **ReportLab / PDF processing** (PDF generation)
- Custom PDF template rendering

---

## 📁 Project Structure

ramadan-pdf-api/
│── app.py
│── ramadan_calendar_to_pdf.py
│── template.pdf
│── Janna LT Bold.ttf
│── requirements.txt
│── Procfile
│── runtime.txt

---

## 📦 Installation

```bash
git clone https://github.com/jaradm/ramadan-pdf-api.git
cd ramadan-pdf-api
```

```bash
python -m venv venv
source venv/bin/activate   # Mac/Linux
venv\Scripts\activate      # Windows
```

```bash
pip install -r requirements.txt
```

---

## ▶️ Running the App

```bash
python app.py
```

Server will run on:

http://localhost:5000

---

## 📡 API Usage

### Generate Ramadan PDF

**POST** `/generate`

#### Example Request

```json
{
  "city": "Chicago",
  "year": 2026
}
```

#### Response

- Returns a generated **PDF file**
- Content-Type: `application/pdf`

---

## 📄 How It Works

1. Request is sent to the API  
2. Data is passed to `ramadan_calendar_to_pdf.py`  
3. The script:
   - Loads `template.pdf`
   - Inserts Ramadan dates & prayer times
   - Applies Arabic font styling  
4. Returns the final generated PDF  

---

## ☁️ Deployment (Heroku)

```bash
heroku create
git push heroku main
```

---

## ⚙️ Configuration

You can customize:

- PDF layout (edit `template.pdf`)
- Font (replace `.ttf` file)
- Calendar logic (edit `ramadan_calendar_to_pdf.py`)

---

## 💡 Use Cases

- Mosque Ramadan schedules  
- Community event PDFs  
- Printable Ramadan calendars  
- Islamic apps & services  

---

## 🤝 Contributing

1. Fork the repo  
2. Create a new branch  
3. Commit your changes  
4. Push your branch  
5. Open a Pull Request  

---

## 📜 License

Add your license here (MIT recommended).

---

## 👤 Author

**Muhammad Jamal Jarad**

# TicketFusion Web Deployment Guide

## For Colleagues - Quick Access Options

### 🌐 Option 1: Streamlit Cloud (Easiest - No Setup Required)

**What it is**: Free cloud hosting for Streamlit apps
**Best for**: Sharing with colleagues who just need to use the app

**Steps:**
1. Visit [share.streamlit.io](https://share.streamlit.io)
2. Sign in with GitHub
3. Click "New app" 
4. Select this repository: `Barry-Eisenberg/TicketFusion`
5. Set main file path: `main.py`
6. Click "Deploy"
7. Share the generated URL (e.g., `https://ticketfusion.streamlit.app`)

**Pros:** 
- ✅ Zero setup for users
- ✅ Always up-to-date with latest code
- ✅ Free for public repos
- ✅ Automatic HTTPS

### 🐳 Option 2: Docker Deployment (Recommended for Production)

**What it is**: Containerized deployment you control
**Best for**: Production use, private networks, or when you need full control

**Quick Deploy:**
```bash
# Pull and run the image
docker run --rm -p 8080:8080 ticketfusion:latest

# Or with persistent data
docker run --rm -p 8080:8080 -v ./data:/app/data ticketfusion:latest
```

**Custom Build & Deploy:**
```bash
# Build from source
git clone https://github.com/Barry-Eisenberg/TicketFusion.git
cd TicketFusion
docker build -t ticketfusion:latest .
docker run --rm -p 8080:8080 ticketfusion:latest
```

Then share: `http://YOUR-SERVER-IP:8080`

### 💻 Option 3: Local Python Installation

**What it is**: Run directly with Python
**Best for**: Development, testing, or when Docker isn't available

**Steps:**
```bash
git clone https://github.com/Barry-Eisenberg/TicketFusion.git
cd TicketFusion
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python -m streamlit run main.py
```

Access at: `http://localhost:8501`

## 🚀 Cloud Platform Deployment

### Heroku
1. Install [Heroku CLI](https://devcenter.heroku.com/articles/heroku-cli)
2. Create `Procfile`: `web: streamlit run main.py --server.port=$PORT --server.address=0.0.0.0`
3. Deploy:
   ```bash
   heroku create your-app-name
   git push heroku main
   ```

### Railway
1. Connect your GitHub repo to [Railway](https://railway.app)
2. Set start command: `streamlit run main.py --server.port=$PORT --server.address=0.0.0.0`
3. Deploy automatically

### Google Cloud Run
```bash
# Build and deploy
gcloud builds submit --tag gcr.io/YOUR-PROJECT/ticketfusion
gcloud run deploy --image gcr.io/YOUR-PROJECT/ticketfusion --platform managed --allow-unauthenticated
```

## 🔧 Configuration for Production

### Environment Variables
```bash
# Required for Google Sheets integration
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GOOGLE_SHEETS_DOC_ID=your-sheet-id

# Database (optional, defaults to SQLite)
DB_URL=sqlite:///data.db

# For cloud deployment
PORT=8080
STREAMLIT_SERVER_HEADLESS=true
```

### Security Considerations
- Use environment variables for sensitive data
- Don't commit `service_account.json` to git
- Use HTTPS in production (most cloud platforms provide this automatically)
- Consider authentication for sensitive data

## 📞 Getting Help

**For App Users:**
- Navigate using the sidebar in the web interface
- Check the "System Status" on the home page for any issues

**For Deployment Issues:**
- Ensure all required environment variables are set
- Check that the database is accessible
- Verify Google Sheets permissions if using that feature
- Check the logs for specific error messages

**Contact:** [Your contact information here]
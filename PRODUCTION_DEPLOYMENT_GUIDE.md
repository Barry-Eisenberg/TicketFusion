# 🚀 TicketFusion Production Deployment Guide

## ✅ **Step 1: Commit Production Files to GitHub**

First, ensure all production files are committed to your GitHub repository:

### Files to ensure are in your repository:
- `streamlit_app_production.py` (main production app) 
- `requirements_deploy.txt` (production dependencies)
- `TheaterMapping_v2.csv` (theater-platform mappings)
- `STREAMLIT_SECRETS_READY.toml` (secrets template - **DO NOT commit the actual secrets**)

### Commit commands:
```bash
# From C:\Dev\TicketFusion directory
git add streamlit_app_production.py
git add requirements_deploy.txt  
git add TheaterMapping_v2.csv
git commit -m "Production app ready for deployment"
git push origin production-data
```

---

## 🌐 **Step 2: Deploy to Streamlit Cloud**

### A. Create Streamlit Cloud Account
1. Go to https://share.streamlit.io/
2. Sign in with your GitHub account (Barry-Eisenberg)
3. Authorize Streamlit to access your repositories

### B. Deploy App
1. Click **"New app"**
2. **Repository**: `Barry-Eisenberg/TicketFusion`
3. **Branch**: `production-data` 
4. **Main file path**: `streamlit_app_production.py`
5. **App URL**: Choose something like `ticketfusion-production` or `tf-production`

### C. Advanced Settings
- **Python version**: 3.9+ (should auto-detect)
- **Requirements file**: `requirements_deploy.txt`

---

## 🔐 **Step 3: Configure Secrets**

### A. Add Secrets to Streamlit Cloud
1. After deployment, go to your app dashboard
2. Click **"Manage app"** → **"Secrets"**
3. Copy the ENTIRE contents from `STREAMLIT_SECRETS_READY.toml` 
4. Paste into the Streamlit Cloud secrets editor
5. Click **"Save"**

### B. Verify Secrets Format
Ensure the secrets look exactly like this:
```toml
# Google Sheets Document ID
GOOGLE_SHEETS_DOC_ID = "1nEXhbjCaDumlHp6LuEPlN3dIt86OsjGsKNqpFzPL4DY"

# Google Service Account Configuration
[google_service_account]
type = "service_account"
project_id = "tf-workflow-automation"
private_key_id = "d6ed1e3d6c6d41fcb1d9d7dcd9995476f7d7067e"
private_key = """-----BEGIN PRIVATE KEY-----
[... full private key content ...]
-----END PRIVATE KEY-----"""
client_email = "tf-automation-poc@tf-workflow-automation.iam.gserviceaccount.com"
client_id = "113936139583345371141"
# ... rest of the service account config
```

---

## 🧪 **Step 4: Test Deployment**

### A. Basic Functionality Test
1. Visit your deployed app URL
2. Test the basic interface loads correctly
3. Navigate between Home, Analytics, and Availability Checker tabs

### B. XLSX Upload Test
1. Upload an XLSX file using the sidebar
2. Verify it successfully uploads to Google Sheets
3. Check that Analytics tab auto-loads with data
4. Verify Availability Checker shows events in dropdown

### C. End-to-End Workflow Test
1. **Upload**: XLSX → Google Sheets conversion
2. **Analytics**: Auto-loading dashboard with visualizations  
3. **Availability**: Platform selection → Event selection → Availability analysis

---

## 👥 **Step 5: Share with Colleagues**

### A. Get Deployment URL
Your app will be available at:
`https://[your-app-name].streamlit.app/`

### B. Access Instructions for Colleagues
```
🎫 TicketFusion Production App

URL: https://[your-app-name].streamlit.app/

How to use:
1. Upload XLSX file using sidebar
2. Wait for Google Sheets conversion 
3. Navigate to Analytics for dashboard
4. Use Availability Checker for ticket analysis

Features:
✅ XLSX upload with automatic Google Sheets conversion
✅ Analytics dashboard with auto-loading
✅ Availability Checker with platform-based filtering
✅ Persistent data across all tabs
```

---

## 🔧 **Troubleshooting**

### Common Issues:

**1. "SpreadsheetNotFound" Error**
- Check that service account has access to template sheet
- Verify sheet ID is correct: `1HcNCioqz8azE51WMF-XAux6byVKfuU_vgqUCbTLVt34`

**2. Secrets Not Working**
- Ensure private key formatting is exact (including line breaks)
- Verify all required fields are present in secrets

**3. Module Import Errors**
- Check `requirements_deploy.txt` includes all dependencies
- Verify Python version compatibility

**4. Theater Mapping Issues**
- Ensure `TheaterMapping_v2.csv` is in repository root
- Check CSV formatting and column names

---

## 📋 **Production Files Checklist**

- [ ] `streamlit_app_production.py` - Main application
- [ ] `requirements_deploy.txt` - Dependencies with openpyxl
- [ ] `TheaterMapping_v2.csv` - Platform mappings  
- [ ] Secrets configured in Streamlit Cloud
- [ ] App deployed and accessible
- [ ] XLSX upload tested
- [ ] Analytics auto-loading confirmed
- [ ] Availability Checker working
- [ ] Colleagues have access URL

---

**🎉 Deployment Complete!**

Your TicketFusion production app should now be live and accessible to your colleagues via the web!
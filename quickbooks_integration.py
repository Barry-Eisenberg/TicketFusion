# quickbooks_integration.py
"""
QuickBooks API integration for TicketFusion
Provides real-time financial data: cash inflows, outflows, and balance
"""

import streamlit as st
import pandas as pd
import requests
from requests_oauthlib import OAuth2Session
from datetime import datetime, timedelta
import json
from typing import Optional, Dict, List, Tuple
import time

# QuickBooks API configuration
QUICKBOOKS_BASE_URL = "https://quickbooks.api.intuit.com"
QUICKBOOKS_SANDBOX_URL = "https://sandbox-quickbooks.api.intuit.com"

class QuickBooksIntegration:
    def __init__(self, sandbox: bool = False):
        self.base_url = QUICKBOOKS_SANDBOX_URL if sandbox else QUICKBOOKS_BASE_URL
        self.client_id = None
        self.client_secret = None
        self.redirect_uri = None
        self.company_id = None
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None

    def configure_from_secrets(self) -> bool:
        """Configure QuickBooks integration from Streamlit secrets"""
        try:
            qb_secrets = st.secrets.get("quickbooks", {})

            self.client_id = qb_secrets.get("client_id")
            self.client_secret = qb_secrets.get("client_secret")
            self.redirect_uri = qb_secrets.get("redirect_uri", "http://localhost:8501")
            self.company_id = qb_secrets.get("company_id")
            self.access_token = qb_secrets.get("access_token")
            self.refresh_token = qb_secrets.get("refresh_token")

            # Check if we have valid tokens
            if not all([self.client_id, self.client_secret, self.company_id]):
                return False

            return True
        except Exception:
            return False

    def get_authorization_url(self) -> str:
        """Generate OAuth2 authorization URL"""
        if not self.client_id or not self.redirect_uri:
            raise ValueError("Client ID and redirect URI must be configured")

        oauth = OAuth2Session(
            self.client_id,
            redirect_uri=self.redirect_uri,
            scope=['com.intuit.quickbooks.accounting']
        )

        authorization_url, state = oauth.authorization_url(
            'https://appcenter.intuit.com/connect/oauth2'
        )

        # Store state in session for verification
        st.session_state['oauth_state'] = state

        return authorization_url

    def exchange_code_for_tokens(self, authorization_code: str, state: str) -> bool:
        """Exchange authorization code for access and refresh tokens"""
        if state != st.session_state.get('oauth_state'):
            st.error("OAuth state mismatch - possible security issue")
            return False

        oauth = OAuth2Session(
            self.client_id,
            redirect_uri=self.redirect_uri,
            scope=['com.intuit.quickbooks.accounting']
        )

        try:
            token = oauth.fetch_token(
                'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer',
                code=authorization_code,
                client_secret=self.client_secret
            )

            self.access_token = token['access_token']
            self.refresh_token = token['refresh_token']
            self.token_expires_at = datetime.now() + timedelta(seconds=token['expires_in'])

            # Store tokens in session state
            st.session_state['qb_access_token'] = self.access_token
            st.session_state['qb_refresh_token'] = self.refresh_token
            st.session_state['qb_token_expires'] = self.token_expires_at.isoformat()

            return True
        except Exception as e:
            st.error(f"Failed to exchange code for tokens: {e}")
            return False

    def refresh_access_token(self) -> bool:
        """Refresh the access token using refresh token"""
        if not self.refresh_token:
            return False

        data = {
            'grant_type': 'refresh_token',
            'refresh_token': self.refresh_token
        }

        try:
            response = requests.post(
                'https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer',
                data=data,
                auth=(self.client_id, self.client_secret)
            )

            if response.status_code == 200:
                token = response.json()
                self.access_token = token['access_token']
                self.refresh_token = token['refresh_token']
                self.token_expires_at = datetime.now() + timedelta(seconds=token['expires_in'])

                # Update session state
                st.session_state['qb_access_token'] = self.access_token
                st.session_state['qb_refresh_token'] = self.refresh_token
                st.session_state['qb_token_expires'] = self.token_expires_at.isoformat()

                return True
            else:
                st.error(f"Failed to refresh token: {response.text}")
                return False
        except Exception as e:
            st.error(f"Error refreshing token: {e}")
            return False

    def _ensure_valid_token(self) -> bool:
        """Ensure we have a valid access token"""
        # Load from session state if available
        if 'qb_access_token' in st.session_state:
            self.access_token = st.session_state['qb_access_token']
            self.refresh_token = st.session_state['qb_refresh_token']
            self.token_expires_at = datetime.fromisoformat(st.session_state['qb_token_expires'])

        if not self.access_token:
            return False

        # Check if token is expired or will expire soon
        if datetime.now() >= (self.token_expires_at - timedelta(minutes=5)):
            return self.refresh_access_token()

        return True

    def _make_api_request(self, endpoint: str, params: Optional[Dict] = None) -> Optional[Dict]:
        """Make authenticated API request to QuickBooks"""
        if not self._ensure_valid_token():
            st.error("No valid QuickBooks access token. Please authenticate.")
            return None

        url = f"{self.base_url}/v3/company/{self.company_id}/{endpoint}"

        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Accept': 'application/json',
            'Content-Type': 'application/json'
        }

        try:
            response = requests.get(url, headers=headers, params=params)

            if response.status_code == 200:
                return response.json()
            elif response.status_code == 401:
                # Token might be expired, try refreshing
                if self.refresh_access_token():
                    headers['Authorization'] = f'Bearer {self.access_token}'
                    response = requests.get(url, headers=headers, params=params)
                    if response.status_code == 200:
                        return response.json()

                st.error("QuickBooks authentication failed. Please re-authenticate.")
                return None
            else:
                st.error(f"QuickBooks API error: {response.status_code} - {response.text}")
                return None

        except Exception as e:
            st.error(f"Error calling QuickBooks API: {e}")
            return None

    def get_company_info(self) -> Optional[Dict]:
        """Get basic company information"""
        return self._make_api_request("companyinfo")

    def get_accounts(self, account_type: Optional[str] = None) -> Optional[List[Dict]]:
        """Get chart of accounts, optionally filtered by type"""
        params = {}
        if account_type:
            params['fetchAll'] = 'false'
            params['q'] = f"Type = '{account_type}'"

        response = self._make_api_request("accounts", params)
        if response and 'QueryResponse' in response:
            return response['QueryResponse'].get('Account', [])
        return []

    def get_cash_accounts(self) -> List[Dict]:
        """Get all cash and bank accounts"""
        cash_accounts = []
        account_types = ['Bank', 'Other Current Asset']  # Bank accounts and petty cash

        for acc_type in account_types:
            accounts = self.get_accounts(acc_type)
            if accounts:
                # Filter for accounts that are likely cash/bank
                for account in accounts:
                    account_name = account.get('Name', '').lower()
                    account_type = account.get('AccountType', '').lower()

                    # Include checking, savings, cash accounts
                    if any(keyword in account_name or keyword in account_type
                          for keyword in ['checking', 'savings', 'cash', 'bank', 'petty']):
                        cash_accounts.append(account)

        return cash_accounts

    def get_account_balance(self, account_id: str, as_of_date: Optional[str] = None) -> Optional[float]:
        """Get the current balance of a specific account"""
        params = {}
        if as_of_date:
            params['date'] = as_of_date

        response = self._make_api_request(f"account/{account_id}", params)
        if response and 'Account' in response:
            account = response['Account']
            return account.get('CurrentBalance', 0)
        return None

    def get_transactions(self, account_id: str, start_date: str, end_date: str,
                        transaction_type: str = 'all') -> List[Dict]:
        """Get transactions for an account within a date range"""
        params = {
            'start_date': start_date,
            'end_date': end_date,
            'fetchAll': 'false'
        }

        # Build query based on transaction type
        if transaction_type == 'deposits':
            query = f"TxnDate >= '{start_date}' AND TxnDate <= '{end_date}' AND DepositAccountRef = '{account_id}'"
        elif transaction_type == 'payments':
            query = f"TxnDate >= '{start_date}' AND TxnDate <= '{end_date}' AND PaymentMethodRef IS NOT NULL"
        else:
            query = f"TxnDate >= '{start_date}' AND TxnDate <= '{end_date}'"

        params['q'] = query

        # Try different transaction endpoints
        endpoints = ['transactions', 'deposits', 'payments', 'transfers']

        all_transactions = []
        for endpoint in endpoints:
            response = self._make_api_request(endpoint, params)
            if response and 'QueryResponse' in response:
                transactions = response['QueryResponse'].get(endpoint.title(), [])
                if transactions:
                    all_transactions.extend(transactions)

        return all_transactions

    def get_cash_flow_summary(self, days: int = 30) -> Dict:
        """Get cash flow summary for the specified number of days"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=days)

        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        # Get cash accounts
        cash_accounts = self.get_cash_accounts()

        total_balance = 0
        total_inflows = 0
        total_outflows = 0

        for account in cash_accounts:
            account_id = account['Id']

            # Get current balance
            balance = self.get_account_balance(account_id)
            if balance is not None:
                total_balance += balance

            # Get transactions for the period
            transactions = self.get_transactions(account_id, start_date_str, end_date_str)

            for txn in transactions:
                amount = txn.get('Amount', 0)

                # Determine if inflow or outflow based on transaction type and account
                txn_type = txn.get('TxnType', '')

                if txn_type in ['Deposit', 'Payment', 'Invoice', 'SalesReceipt']:
                    if amount > 0:
                        total_inflows += amount
                    else:
                        total_outflows += abs(amount)
                elif txn_type == 'Expense':
                    total_outflows += abs(amount)
                elif txn_type == 'Transfer':
                    # For transfers, we need to check if it's to/from this account
                    # This is simplified - in practice, you'd check the FromAccountRef/ToAccountRef
                    if amount > 0:
                        total_inflows += amount
                    else:
                        total_outflows += abs(amount)

        return {
            'total_balance': total_balance,
            'total_inflows': total_inflows,
            'total_outflows': total_outflows,
            'net_cash_flow': total_inflows - total_outflows,
            'period_days': days,
            'start_date': start_date_str,
            'end_date': end_date_str,
            'cash_accounts_count': len(cash_accounts)
        }

    def get_recent_transactions(self, limit: int = 50) -> List[Dict]:
        """Get recent transactions across all accounts"""
        end_date = datetime.now()
        start_date = end_date - timedelta(days=90)  # Look back 90 days for recent activity

        start_date_str = start_date.strftime('%Y-%m-%d')
        end_date_str = end_date.strftime('%Y-%m-%d')

        cash_accounts = self.get_cash_accounts()
        all_transactions = []

        for account in cash_accounts:
            account_id = account['Id']
            transactions = self.get_transactions(account_id, start_date_str, end_date_str)

            # Add account name to each transaction
            for txn in transactions:
                txn['AccountName'] = account.get('Name', 'Unknown Account')
                txn['AccountType'] = account.get('AccountType', 'Unknown Type')

            all_transactions.extend(transactions)

        # Sort by date (most recent first) and limit
        all_transactions.sort(key=lambda x: x.get('TxnDate', ''), reverse=True)
        return all_transactions[:limit]


# Global QuickBooks integration instance
qb_integration = QuickBooksIntegration(sandbox=False)


def init_quickbooks_integration():
    """Initialize QuickBooks integration from secrets"""
    global qb_integration

    if qb_integration.configure_from_secrets():
        st.sidebar.success("✅ QuickBooks Connected")
        return True
    else:
        st.sidebar.warning("⚠️ QuickBooks Not Configured")
        return False


def show_quickbooks_auth_ui():
    """Show QuickBooks authentication UI in sidebar"""
    st.sidebar.subheader("🔗 QuickBooks Integration")

    if not qb_integration.configure_from_secrets():
        st.sidebar.info("QuickBooks not configured. Add credentials to secrets.")
        return

    # Check if we have valid tokens
    if 'qb_access_token' in st.session_state and qb_integration._ensure_valid_token():
        st.sidebar.success("✅ QuickBooks Connected")

        # Show connection status
        if st.sidebar.button("🔄 Refresh Connection"):
            if qb_integration.refresh_access_token():
                st.success("Connection refreshed!")
                st.rerun()
            else:
                st.error("Failed to refresh connection")

        # Show disconnect option
        if st.sidebar.button("🚪 Disconnect"):
            for key in ['qb_access_token', 'qb_refresh_token', 'qb_token_expires']:
                if key in st.session_state:
                    del st.session_state[key]
            st.success("Disconnected from QuickBooks")
            st.rerun()

    else:
        # Show authentication flow
        st.sidebar.info("Connect to QuickBooks to access real-time financial data")

        if st.sidebar.button("🔐 Connect to QuickBooks"):
            try:
                auth_url = qb_integration.get_authorization_url()
                st.sidebar.markdown(f"[Click here to authorize]({auth_url})")
                st.sidebar.info("After authorizing, paste the authorization code below:")

                auth_code = st.sidebar.text_input("Authorization Code:", type="password")
                if st.sidebar.button("✅ Complete Authentication") and auth_code:
                    if qb_integration.exchange_code_for_tokens(auth_code, st.session_state.get('oauth_state', '')):
                        st.success("Successfully connected to QuickBooks!")
                        st.rerun()
                    else:
                        st.error("Authentication failed. Please try again.")

            except Exception as e:
                st.sidebar.error(f"Error: {e}")


def get_quickbooks_financial_data() -> Optional[Dict]:
    """Get financial data from QuickBooks for display"""
    if not qb_integration._ensure_valid_token():
        return None

    try:
        # Get cash flow summary for last 30 days
        cash_flow = qb_integration.get_cash_flow_summary(days=30)

        # Get recent transactions
        recent_txns = qb_integration.get_recent_transactions(limit=20)

        return {
            'cash_flow': cash_flow,
            'recent_transactions': recent_txns
        }
    except Exception as e:
        st.error(f"Error fetching QuickBooks data: {e}")
        return None
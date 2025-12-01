# web_dashboard.py (UPDATED)

from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, db
import json
from datetime import datetime
import os
import sys

app = Flask(__name__)

# --- CONFIGURATION ---
FIREBASE_DATABASE_URL = 'https://heriwadi-bookshop-default-rtdb.firebaseio.com/'

# Initialize Firebase (Keep this section as is)
try:
    cred_json_str = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    
    # ... (Initialization logic is the same) ...
        
    else:
        print("⚠️ FIREBASE_CREDENTIALS_JSON environment variable not found.")
        print("🔴 Dashboard will fail to fetch live data. Please check Render configuration.")
        
except Exception as e:
    print(f"❌ Firebase initialization failed: {e}")
    # ... (Error handling is the same) ...

# --- HELPER FUNCTION ---
def get_safe_sales_data():
    """Fetches sales and ensures it is a dictionary (key: sale_data) for iteration."""
    try:
        ref = db.reference('/sales')
        sales_data = ref.get()
        
        if sales_data is None:
            return {}
        
        # CRITICAL FIX: If Firebase returns a list (due to array-like structure), convert it 
        # to a dictionary using simple integer keys for consistency with .items() logic.
        if isinstance(sales_data, list):
            # This handles the 'list' object has no attribute 'values' error
            return {str(i): item for i, item in enumerate(sales_data) if item is not None}
            
        return sales_data
        
    except Exception as e:
        print(f"❌ Error in get_safe_sales_data: {e}")
        return {}

# --- FLASK ROUTES (UPDATED) ---

@app.route('/')
def dashboard():
    """Renders the main dashboard HTML template."""
    return render_template('index.html')

@app.route('/api/sales')
def get_sales():
    """Fetches and formats recent sales for the activity feed."""
    try:
        # Use order_by_child and limit_to_last to get the latest sales efficiently
        ref = db.reference('/sales')
        sales_data = ref.order_by_child('timestamp').limit_to_last(50).get()
        
        # CRITICAL FIX: Handle list-like or None data from the ordered query
        if isinstance(sales_data, list):
            # Convert to dictionary-like structure for the dashboard frontend 
            sales_data = {str(i): item for i, item in enumerate(sales_data) if item is not None}
        
        if sales_data:
            sales = []
            for key, value in sales_data.items():
                sales.append({
                    'id': value.get('sale_id', key), # Use key if sale_id is missing
                    'amount': value.get('total_amount', 0),
                    'payment_method': value.get('payment_method', 'N/A'),
                    'timestamp': value.get('timestamp', ''),
                    'items_count': len(value.get('items', []))
                })
            return jsonify(sales[::-1])
            
    except Exception as e:
        print(f"❌ Error fetching sales: {e}")
        import traceback
        traceback.print_exc()
    
    return jsonify([])

@app.route('/api/stats')
def get_stats():
    """Calculates and returns total sales, transactions, and today's sales."""
    try:
        sales_data = get_safe_sales_data() # Use the safe helper
        
        if not sales_data:
            return jsonify({
                'total_sales': 0,
                'total_transactions': 0,
                'today_sales': 0
            })
        
        total_sales = 0.0
        total_transactions = 0
        today_sales = 0.0
        
        today = datetime.now().date()
        
        # Iterate over the safe dictionary keys and values
        for sale_id, sale in sales_data.items():
            total_amount = sale.get('total_amount', 0)
            timestamp_str = sale.get('timestamp')

            total_sales += total_amount
            total_transactions += 1
            
            if timestamp_str:
                try:
                    sale_date = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).date() # Handle 'Z' format
                    if sale_date == today:
                        today_sales += total_amount
                except ValueError as e:
                    print(f"⚠️ Invalid timestamp '{timestamp_str}': {e}")
        
        result = {
            'total_sales': round(total_sales, 2),
            'total_transactions': total_transactions,
            'today_sales': round(today_sales, 2)
        }
        
        return jsonify(result)
        
    except Exception as e:
        print(f"❌ Error fetching stats: {e}")
        import traceback
        traceback.print_exc()
    
    return jsonify({
        'total_sales': 0,
        'total_transactions': 0,
        'today_sales': 0
    })

@app.route('/api/recent-activity')
def get_recent_activity():
    """Fetches and formats the 10 most recent activities."""
    # This route is similar to get_sales, so using the same fix logic
    try:
        ref = db.reference('/sales')
        sales_data = ref.order_by_child('timestamp').limit_to_last(10).get()
        
        # CRITICAL FIX: Handle list-like or None data
        if isinstance(sales_data, list):
            sales_data = {str(i): item for i, item in enumerate(sales_data) if item is not None}
        
        if sales_data:
            activity = []
            # Iterate over the dictionary items
            for key, value in sales_data.items():
                activity.append({
                    'type': 'sale',
                    'message': f"Sale #{value.get('sale_id', key)} - KES {value.get('total_amount', 0):.2f}",
                    'timestamp': value.get('timestamp', '')
                })
            # Reverse for most recent first
            return jsonify(activity[::-1])
    except Exception as e:
        print(f"❌ Error fetching activity: {e}")
        import traceback
        traceback.print_exc()
    
    return jsonify([])

@app.route('/api/debug')
def debug():
    """Debug endpoint to check Firebase data structure (UPDATED)"""
    try:
        sales_data = get_safe_sales_data() # Use the safe helper
        
        sales_keys = list(sales_data.keys())
        sales_sample = [sales_data[k] for k in sales_keys[:2]] # Safely access sample data
        
        summary_ref = db.reference('/daily_sales')
        summary_data = summary_ref.get()
        
        return jsonify({
            'sales_count': len(sales_data) if sales_data else 0,
            # CRITICAL FIX: We are using keys() and indexing to safely access elements
            'sales_sample': sales_sample, 
            'daily_summary': summary_data,
            'firebase_url': FIREBASE_DATABASE_URL,
            'env_var_set': bool(os.environ.get('FIREBASE_CREDENTIALS_JSON'))
        })
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc(),
            'env_var_set': bool(os.environ.get('FIREBASE_CREDENTIALS_JSON'))
        })

@app.route('/health')
def health():
    # ... (Health check is the same) ...
    
if __name__ == '__main__':
    # ... (Run command is the same) ...

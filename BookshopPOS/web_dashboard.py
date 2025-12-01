# web_dashboard.py (Final Fix for Deployment & Data Structure)

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

# Global variable to track Firebase initialization status
firebase_initialized = False

# Initialize Firebase (Robust initialization)
try:
    cred_json_str = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    
    if cred_json_str:
        # Load the credentials safely
        try:
            cred_info = json.loads(cred_json_str)
            cred = credentials.Certificate(cred_info)
            
            firebase_admin.initialize_app(cred, {
                'databaseURL': FIREBASE_DATABASE_URL
            })
            print("✅ Firebase initialized successfully from Environment Variable.")
            firebase_initialized = True
        except Exception as json_e:
            print(f"❌ Error loading or initializing Firebase credentials: {json_e}")
            import traceback
            traceback.print_exc()
            
    else:
        print("⚠️ FIREBASE_CREDENTIALS_JSON environment variable not found.")
        print("🔴 Dashboard will operate with mocked/zero data until configured.")
        
except Exception as e:
    print(f"❌ Critical Firebase initialization failed (Outside credential block): {e}")
    import traceback
    traceback.print_exc()

# --- HELPER FUNCTION (CRITICAL FIX FOR 'list' object error) ---

def get_safe_sales_data():
    """Fetches sales and ensures it is a dictionary for iteration (fixes 'list' object has no attribute 'values')."""
    if not firebase_initialized:
        print("⚠️ Firebase not initialized. Returning empty data.")
        return {}
        
    try:
        ref = db.reference('/sales')
        sales_data = ref.get()
        
        if sales_data is None:
            return {}
        
        # This handles the case where Firebase returns a list of items instead of a dict of keys.
        if isinstance(sales_data, list):
            # Convert list to dictionary using indices as keys. Filter out None entries.
            # This allows safe use of .items() or .values() in subsequent functions.
            return {str(i): item for i, item in enumerate(sales_data) if item is not None}
            
        return sales_data
        
    except Exception as e:
        print(f"❌ Error in get_safe_sales_data: {e}")
        import traceback
        traceback.print_exc()
        return {}

# --- FLASK ROUTES ---

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
        
        # Apply the same list-to-dict conversion logic if order_by_child returns a list
        if isinstance(sales_data, list):
            sales_data = {str(i): item for i, item in enumerate(sales_data) if item is not None}
        
        if sales_data:
            sales = []
            # Iterate over the resulting dictionary keys and values
            for key, value in sales_data.items():
                sales.append({
                    'id': value.get('sale_id', key),
                    'amount': value.get('total_amount', 0),
                    'payment_method': value.get('payment_method', 'N/A'),
                    # Handle Z suffix for ISO 8601 parsing on some systems
                    'timestamp': value.get('timestamp', '').replace('Z', '+00:00'),
                    'items_count': len(value.get('items', []))
                })
            # Reverse sales to show newest first, as limit_to_last returns oldest first
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
        
        # Use simple date format for comparison
        today = datetime.now().strftime('%Y-%m-%d')
        
        # Iterate over the safe dictionary keys and values
        for sale_id, sale in sales_data.items():
            total_amount = sale.get('total_amount', 0)
            timestamp_str = sale.get('timestamp')

            total_sales += total_amount
            total_transactions += 1
            
            if timestamp_str:
                try:
                    # Parse timestamp and compare date part only
                    sale_date_str = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00')).strftime('%Y-%m-%d')
                    if sale_date_str == today:
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
    try:
        ref = db.reference('/sales')
        sales_data = ref.order_by_child('timestamp').limit_to_last(10).get()
        
        # Apply the same list-to-dict conversion logic
        if isinstance(sales_data, list):
            sales_data = {str(i): item for i, item in enumerate(sales_data) if item is not None}
        
        if sales_data:
            activity = []
            # Iterate over the resulting dictionary keys and values
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
    """Debug endpoint to check Firebase data structure"""
    try:
        sales_data = get_safe_sales_data() # Use the safe helper
        
        sales_keys = list(sales_data.keys()) if sales_data else []
        sales_sample = [sales_data[k] for k in sales_keys[:2]] # Safely access sample data
        
        summary_ref = db.reference('/daily_sales')
        summary_data = summary_ref.get()
        
        return jsonify({
            'sales_count': len(sales_data) if sales_data else 0,
            'sales_sample': sales_sample, 
            'daily_summary': summary_data,
            'firebase_url': FIREBASE_DATABASE_URL,
            'env_var_set': bool(os.environ.get('FIREBASE_CREDENTIALS_JSON')),
            'firebase_initialized': firebase_initialized
        })
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc(),
            'env_var_set': bool(os.environ.get('FIREBASE_CREDENTIALS_JSON')),
            'firebase_initialized': firebase_initialized
        })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

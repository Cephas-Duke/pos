from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, db
import json
from datetime import datetime, timedelta
import os
import sys

app = Flask(__name__)

# --- CONFIGURATION ---
# Ensure this URL matches the one in your POS code
FIREBASE_DATABASE_URL = 'https://heriwadi-bookshop-default-rtdb.firebaseio.com/'
firebase_initialized = False

# --- INITIALIZATION ---
try:
    cred_json_str = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    if cred_json_str:
        try:
            cred_info = json.loads(cred_json_str)
            cred = credentials.Certificate(cred_info)
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred, {'databaseURL': FIREBASE_DATABASE_URL})
            print("✅ Firebase initialized successfully.")
            firebase_initialized = True
        except Exception as json_e:
            print(f"❌ Error loading credentials: {json_e}")
    else:
        print("⚠️ FIREBASE_CREDENTIALS_JSON not found. Running in offline mode.")
except Exception as e:
    print(f"❌ Critical Initialization Error: {e}")

# --- HELPER FUNCTIONS ---
def get_safe_sales_data():
    """Fetches ALL sales and ensures it is a dictionary."""
    if not firebase_initialized: return {}
    try:
        ref = db.reference('/sales')
        sales_data = ref.get()
        if sales_data is None: return {}
        if isinstance(sales_data, list):
            return {str(i): item for i, item in enumerate(sales_data) if item is not None}
        return sales_data
    except Exception as e:
        print(f"❌ Error in get_safe_sales_data: {e}")
        return {}

def parse_date(date_str):
    """Robust date parser handling POS format and ISO format."""
    try:
        # Try POS format first (YYYY-MM-DD HH:MM:SS)
        return datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
    except:
        try:
            # Try ISO format (YYYY-MM-DDTHH:MM:SS...)
            return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        except:
            return None

# --- ROUTES ---

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/stats')
def get_stats():
    try:
        sales_data = get_safe_sales_data()
        total_sales = 0.0
        total_transactions = 0
        today_sales = 0.0
        today = datetime.now().strftime('%Y-%m-%d')
        
        for _, sale in sales_data.items():
            # Get amount
            try:
                amt = float(sale.get('total_amount', 0))
            except:
                amt = 0.0

            total_sales += amt
            total_transactions += 1
            
            # Get date
            ts = sale.get('timestamp') or sale.get('sale_date')
            if ts:
                dt_obj = parse_date(ts)
                if dt_obj and dt_obj.strftime('%Y-%m-%d') == today:
                    today_sales += amt

        return jsonify({
            'total_sales': round(total_sales, 2),
            'total_transactions': total_transactions,
            'today_sales': round(today_sales, 2)
        })
    except Exception as e:
        print(f"Error stats: {e}")
        return jsonify({'total_sales': 0, 'total_transactions': 0, 'today_sales': 0})

@app.route('/api/sales')
def get_recent_sales():
    """Fetches last 20 sales for the table."""
    try:
        if not firebase_initialized: return jsonify([])
        ref = db.reference('/sales')
        # Limit to last 20
        data = ref.order_by_child('timestamp').limit_to_last(20).get()
        
        sales = []
        if data:
            source = data if isinstance(data, list) else data.values()
            for item in source:
                if isinstance(item, dict):
                    sales.append({
                        'id': item.get('sale_id', 'N/A'),
                        'amount': item.get('total_amount', 0),
                        'method': item.get('payment_method', 'Cash'),
                        'timestamp': item.get('timestamp', ''),
                        'items': len(item.get('items', []))
                    })
        # Return reversed (newest first)
        return jsonify(sales[::-1])
    except Exception as e:
        return jsonify([])

@app.route('/api/charts')
def get_chart_data():
    """Aggregates data for the Dashboard Charts."""
    try:
        sales_data = get_safe_sales_data()
        
        # 1. Payment Method Stats
        methods = {}
        
        # 2. Weekly Trends (Last 7 days)
        today = datetime.now().date()
        last_7_days = [(today - timedelta(days=i)) for i in range(6, -1, -1)] 
        daily_totals = {d.strftime('%Y-%m-%d'): 0.0 for d in last_7_days}
        
        for _, sale in sales_data.items():
            # Method Count
            pm = sale.get('payment_method', 'Unknown')
            methods[pm] = methods.get(pm, 0) + 1
            
            # Daily Sum
            ts = sale.get('timestamp') or sale.get('sale_date')
            if ts:
                dt_obj = parse_date(ts)
                if dt_obj:
                    d_str = dt_obj.strftime('%Y-%m-%d')
                    if d_str in daily_totals:
                        try:
                            daily_totals[d_str] += float(sale.get('total_amount', 0))
                        except: pass

        return jsonify({
            'payment_methods': {
                'labels': list(methods.keys()),
                'data': list(methods.values())
            },
            'weekly_sales': {
                'labels': [d.strftime('%a %d') for d in last_7_days], 
                'data': list(daily_totals.values())
            }
        })
    except Exception as e:
        print(e)
        return jsonify({})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)

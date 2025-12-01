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

# Initialize Firebase
try:
    cred_json_str = os.environ.get('FIREBASE_CREDENTIALS_JSON')
    
    if cred_json_str:
        cred_info = json.loads(cred_json_str)
        cred = credentials.Certificate(cred_info)
        
        firebase_admin.initialize_app(cred, {
            'databaseURL': FIREBASE_DATABASE_URL
        })
        print("✅ Firebase initialized successfully from Environment Variable.")
        
    else:
        print("⚠️ FIREBASE_CREDENTIALS_JSON environment variable not found.")
        print("🔴 Dashboard will fail to fetch live data. Please check Render configuration.")
        # Don't exit in production - allow app to start
        # sys.exit(1) 
        
except Exception as e:
    print(f"❌ Firebase initialization failed: {e}")
    import traceback
    traceback.print_exc()
    # Don't exit - let app start anyway
    # sys.exit(1)

# --- FLASK ROUTES ---

@app.route('/')
def dashboard():
    """Renders the main dashboard HTML template."""
    return render_template('index.html')

@app.route('/api/sales')
def get_sales():
    """Fetches and formats recent sales for the activity feed."""
    try:
        ref = db.reference('/sales')
        sales_data = ref.order_by_child('timestamp').limit_to_last(50).get()
        
        print(f"📊 Sales data fetched: {type(sales_data)}, Count: {len(sales_data) if sales_data else 0}")
        
        if sales_data:
            sales = []
            for key, value in sales_data.items():
                sales.append({
                    'id': value.get('sale_id', ''),
                    'amount': value.get('total_amount', 0),
                    'payment_method': value.get('payment_method', ''),
                    'timestamp': value.get('timestamp', ''),
                    'items_count': len(value.get('items', []))
                })
            print(f"✅ Returning {len(sales)} sales")
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
        ref = db.reference('/sales')
        sales_data = ref.get()
        
        print(f"📊 Stats - Sales data type: {type(sales_data)}")
        
        if not sales_data:
            print("⚠️ No sales data found")
            return jsonify({
                'total_sales': 0,
                'total_transactions': 0,
                'today_sales': 0
            })
        
        total_sales = 0.0
        total_transactions = 0
        today_sales = 0.0
        
        today = datetime.now().date()
        
        for sale_id, sale in sales_data.items():
            total_amount = sale.get('total_amount', 0)
            timestamp_str = sale.get('timestamp')

            total_sales += total_amount
            total_transactions += 1
            
            if timestamp_str:
                try:
                    sale_date = datetime.fromisoformat(timestamp_str).date()
                    if sale_date == today:
                        today_sales += total_amount
                except ValueError as e:
                    print(f"⚠️ Invalid timestamp '{timestamp_str}': {e}")
        
        result = {
            'total_sales': round(total_sales, 2),
            'total_transactions': total_transactions,
            'today_sales': round(today_sales, 2)
        }
        
        print(f"✅ Stats: {result}")
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
        
        if sales_data:
            activity = []
            for key, value in sales_data.items():
                activity.append({
                    'type': 'sale',
                    'message': f"Sale #{value.get('sale_id', '')} - KES {value.get('total_amount', 0):.2f}",
                    'timestamp': value.get('timestamp', '')
                })
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
        sales_ref = db.reference('/sales')
        sales_data = sales_ref.get()
        
        summary_ref = db.reference('/daily_sales')
        summary_data = summary_ref.get()
        
        return jsonify({
            'sales_count': len(sales_data) if sales_data else 0,
            'sales_sample': list(sales_data.values())[:2] if sales_data else [],
            'daily_summary': summary_data,
            'firebase_url': FIREBASE_DATABASE_URL,
            'env_var_set': bool(os.environ.get('FIREBASE_CREDENTIALS_JSON'))
        })
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        })

@app.route('/health')
def health():
    """Health check endpoint"""
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

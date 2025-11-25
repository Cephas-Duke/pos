from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, db
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# Initialize Firebase with environment variables (for Render)
def init_firebase():
    try:
        # Check if we have Firebase credentials in environment
        firebase_creds = os.environ.get('FIREBASE_CREDENTIALS')
        
        if firebase_creds:
            # Parse JSON credentials from environment variable
            cred_dict = json.loads(firebase_creds)
            cred = credentials.Certificate(cred_dict)
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://heriwadi-bookshop-default-rtdb.firebaseio.com'
            })
            print("✅ Firebase initialized with environment credentials")
            return True
            
        elif os.path.exists('firebase-service-account-key.json'):
            # Use local file for development
            cred = credentials.Certificate('firebase-service-account-key.json')
            firebase_admin.initialize_app(cred, {
                'databaseURL': 'https://heriwadi-bookshop-default-rtdb.firebaseio.com'
            })
            print("✅ Firebase initialized with local service account file")
            return True
            
        else:
            print("⚠️  No Firebase credentials found")
            print("Set FIREBASE_CREDENTIALS environment variable or add firebase-service-account-key.json")
            return False
            
    except Exception as e:
        print(f"❌ Firebase initialization failed: {e}")
        return False

# Initialize Firebase
firebase_connected = init_firebase()

@app.route('/')
def dashboard():
    return render_template('index.html')

@app.route('/api/sales')
def get_sales():
    if not firebase_connected:
        return jsonify([])
    
    try:
        ref = db.reference('/sales')
        sales_data = ref.order_by_child('timestamp').limit_to_last(50).get()
        
        if sales_data:
            sales = []
            for key, value in sales_data.items():
                sales.append({
                    'id': value.get('sale_id', ''),
                    'amount': float(value.get('total_amount', 0)),
                    'payment_method': value.get('payment_method', ''),
                    'timestamp': value.get('timestamp', ''),
                    'items_count': len(value.get('items', []))
                })
            return jsonify(sales[::-1])
    except Exception as e:
        print(f"Error fetching sales: {e}")
    
    return jsonify([])

@app.route('/api/stats')
def get_stats():
    if not firebase_connected:
        return jsonify({
            'total_sales': 0,
            'total_transactions': 0,
            'today_sales': 0
        })
    
    try:
        ref = db.reference('/sales')
        sales_data = ref.get()
        
        if sales_data:
            total_sales = sum(float(sale.get('total_amount', 0)) for sale in sales_data.values())
            total_transactions = len(sales_data)
            
            # Today's sales
            today = datetime.now().date()
            today_sales = 0
            
            for sale in sales_data.values():
                try:
                    timestamp = sale.get('timestamp', '')
                    if timestamp:
                        sale_date = datetime.fromisoformat(timestamp.replace('Z', '+00:00')).date()
                        if sale_date == today:
                            today_sales += float(sale.get('total_amount', 0))
                except Exception as date_error:
                    print(f"Date parsing error: {date_error}")
                    pass
            
            return jsonify({
                'total_sales': round(total_sales, 2),
                'total_transactions': total_transactions,
                'today_sales': round(today_sales, 2)
            })
    except Exception as e:
        print(f"Error fetching stats: {e}")
    
    return jsonify({
        'total_sales': 0,
        'total_transactions': 0,
        'today_sales': 0
    })

@app.route('/api/recent-activity')
def get_recent_activity():
    if not firebase_connected:
        return jsonify([])
    
    try:
        ref = db.reference('/sales')
        sales_data = ref.order_by_child('timestamp').limit_to_last(10).get()
        
        if sales_data:
            activity = []
            for key, value in sales_data.items():
                activity.append({
                    'type': 'sale',
                    'message': f"Sale #{value.get('sale_id', '')} - KES {float(value.get('total_amount', 0)):.2f}",
                    'timestamp': value.get('timestamp', '')
                })
            return jsonify(activity[::-1])
    except Exception as e:
        print(f"Error fetching activity: {e}")
    
    return jsonify([])

@app.route('/api/health')
def health_check():
    return jsonify({
        'status': 'online',
        'firebase_connected': firebase_connected,
        'timestamp': datetime.now().isoformat()
    })

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=False, host='0.0.0.0', port=port)

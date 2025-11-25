from flask import Flask, render_template, jsonify, request
import firebase_admin
from firebase_admin import credentials, db
import json
from datetime import datetime, timedelta
import os

app = Flask(__name__)

# Initialize Firebase
try:
    cred = credentials.Certificate('path/to/your/firebase-service-account-key.json')
    firebase_admin.initialize_app(cred, {
        'databaseURL': 'https://your-project-id.firebaseio.com/'
    })
except:
    print("Firebase initialization failed - using mock data")

@app.route('/')
def dashboard():
    return render_template('dashboard.html')

@app.route('/api/sales')
def get_sales():
    try:
        # Get sales data from Firebase
        ref = db.reference('/sales')
        sales_data = ref.order_by_child('timestamp').limit_to_last(50).get()
        
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
            return jsonify(sales[::-1])  # Reverse to show latest first
    except Exception as e:
        print(f"Error fetching sales: {e}")
    
    # Return empty array if no data
    return jsonify([])

@app.route('/api/stats')
def get_stats():
    try:
        ref = db.reference('/sales')
        sales_data = ref.get()
        
        if sales_data:
            total_sales = sum(sale.get('total_amount', 0) for sale in sales_data.values())
            total_transactions = len(sales_data)
            
            # Today's sales
            today = datetime.now().date()
            today_sales = sum(
                sale.get('total_amount', 0) for sale in sales_data.values()
                if datetime.fromisoformat(sale.get('timestamp', '')).date() == today
            )
            
            return jsonify({
                'total_sales': total_sales,
                'total_transactions': total_transactions,
                'today_sales': today_sales
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
        print(f"Error fetching activity: {e}")
    
    return jsonify([])

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
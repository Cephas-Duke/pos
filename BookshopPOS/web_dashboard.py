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
    """Calculates and returns total sales, transactions, and today's sales"""
    try:
        ref = db.reference('/sales')
        sales_data = ref.get()
        
        print(f"📊 Fetched sales data: {sales_data}")  # Debug log
        
        if not sales_data:
            print("⚠️ No sales data in Firebase")
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
            'total_sales': total_sales,
            'total_transactions': total_transactions,
            'today_sales': today_sales
        }
        
        print(f"✅ Stats calculated: {result}")
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
```

**5. Testing Steps:**

1. **Update Firebase Rules** (as shown above)

2. **Test Desktop POS:**
   - Run `main.py`
   - Make a test sale
   - Check console output - you should see:
```
     ✅ Sale X synced to Firebase
     ✅ Daily summary updated

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

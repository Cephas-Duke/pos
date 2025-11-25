import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import sqlite3
from datetime import datetime
import json
import os
import requests
import threading

class BookshopPOS:
    def __init__(self, root):
        self.root = root
        self.root.title("HERIWADI BOOKSHOP - POS System")
        self.root.geometry("1200x700")
        self.root.configure(bg="#f0f0f0")
        
        # Your actual Firebase configuration
        self.firebase_config = {
            'apiKey': "AIzaSyCcQMjq4OwxondM8kjKgK4xitjk6QLsdg0",
            'databaseURL': "https://heriwadi-bookshop-default-rtdb.firebaseio.com",
            'projectId': "heriwadi-bookshop",
            'storageBucket': "heriwadi-bookshop.firebasestorage.app",
            'messagingSenderId': "1009993842704",
            'appId': "1:1009993842704:web:c308ea85000df2f72eca95"
        }
        
        # Initialize databases
        self.init_database()
        self.init_firebase()
        
        # Cart items
        self.cart = []
        self.cart_total = 0.0
        
        # Create main UI
        self.create_ui()
        
        # Load books into inventory view
        self.refresh_inventory()
        
        print("HERIWADI BOOKSHOP POS System started successfully!")
        if self.firebase_connected:
            print("✅ Firebase connection ready")
        else:
            print("⚠️  Firebase not connected - running in offline mode")

    def init_firebase(self):
        """Initialize Firebase connection"""
        try:
            # Test Firebase configuration
            if (self.firebase_config['databaseURL'] and 
                self.firebase_config['apiKey']):
                
                self.firebase_connected = True
                print(f"✅ Connected to Firebase: {self.firebase_config['databaseURL']}")
                
                # Test the connection by writing a simple message
                self.test_firebase_connection()
                
            else:
                self.firebase_connected = False
                print("❌ Invalid Firebase configuration")
                
        except Exception as e:
            print(f"Firebase initialization error: {e}")
            self.firebase_connected = False

    def test_firebase_connection(self):
        """Test Firebase connection by writing a simple message"""
        try:
            test_data = {
                'message': 'HERIWADI BOOKSHOP POS System Connected Successfully!',
                'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                'system': 'Python POS Desktop App'
            }
            
            url = f"{self.firebase_config['databaseURL']}/connection_test.json"
            response = requests.put(url, json=test_data)
            
            if response.status_code == 200:
                print("✅ Firebase connection test: SUCCESS")
            else:
                print(f"❌ Firebase connection test failed: {response.text}")
                
        except Exception as e:
            print(f"Firebase connection test error: {e}")

    def sync_to_firebase(self, data_type, data):
        """Sync data to Firebase in a separate thread"""
        if not self.firebase_connected:
            return
            
        def sync_thread():
            try:
                timestamp = datetime.now().isoformat()
                
                if data_type == 'sale':
                    sale_data = {
                        'sale_id': data['sale_id'],
                        'total_amount': data['total_amount'],
                        'payment_method': data['payment_method'],
                        'items': data['items'],
                        'timestamp': timestamp,
                        'location': 'HERIWADI_BOOKSHOP',
                        'sync_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'shop_name': 'HERIWADI BOOKSHOP'
                    }
                    
                    # Make HTTP request to Firebase
                    url = f"{self.firebase_config['databaseURL']}/sales/{data['sale_id']}.json"
                    response = requests.put(url, json=sale_data)
                    
                    if response.status_code == 200:
                        print(f"✅ Sale {data['sale_id']} synced to Firebase")
                        
                        # Also update sales summary
                        self.update_sales_summary(data)
                    else:
                        print(f"❌ Failed to sync sale {data['sale_id']}: {response.text}")
                        
                elif data_type == 'inventory_update':
                    # Sync inventory changes
                    inventory_data = {
                        'item_id': data['item_id'],
                        'title': data['title'],
                        'stock_change': data['stock_change'],
                        'new_stock': data['new_stock'],
                        'timestamp': timestamp
                    }
                    url = f"{self.firebase_config['databaseURL']}/inventory_updates/{timestamp}.json"
                    requests.post(url, json=inventory_data)
                    print("✅ Inventory update synced to Firebase")
                    
            except Exception as e:
                print(f"Firebase sync error: {e}")
        
        # Run sync in background thread
        thread = threading.Thread(target=sync_thread)
        thread.daemon = True
        thread.start()

    def update_sales_summary(self, sale_data):
        """Update sales summary in Firebase"""
        try:
            # Update daily summary
            today = datetime.now().strftime('%Y-%m-%d')
            summary_url = f"{self.firebase_config['databaseURL']}/daily_sales/{today}.json"
            
            # Get current daily total
            response = requests.get(summary_url)
            current_data = response.json() or {'total_sales': 0, 'transaction_count': 0}
            
            # Update daily total
            updated_data = {
                'total_sales': current_data.get('total_sales', 0) + sale_data['total_amount'],
                'transaction_count': current_data.get('transaction_count', 0) + 1,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            requests.put(summary_url, json=updated_data)
            print(f"✅ Daily sales summary updated")
            
        except Exception as e:
            print(f"Sales summary update error: {e}")

    def complete_sale(self):
        """Process the sale and sync to Firebase"""
        if not self.cart:
            messagebox.showwarning("Empty Cart", "Please add items to cart")
            return
        
        # Validate payment amount
        try:
            amount_paid_str = self.amount_paid_entry.get().strip()
            if not amount_paid_str:
                messagebox.showwarning("Payment Required", "Please enter the amount paid by customer")
                return
            
            amount_paid = float(amount_paid_str)
            
            if amount_paid < self.cart_total:
                messagebox.showerror("Insufficient Payment", 
                                  f"Amount paid (KES {amount_paid:.2f}) is less than total (KES {self.cart_total:.2f})")
                return
            
            change = amount_paid - self.cart_total
            
        except ValueError:
            messagebox.showerror("Invalid Amount", "Please enter a valid amount")
            return
        
        try:
            # Save sale to database
            sale_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            payment_method = self.payment_var.get()
            items_json = json.dumps(self.cart)
            
            self.cursor.execute('''
                INSERT INTO sales (sale_date, total_amount, payment_method, items_json)
                VALUES (?, ?, ?, ?)
            ''', (sale_date, self.cart_total, payment_method, items_json))
            
            sale_id = self.cursor.lastrowid
            
            # Update stock
            for item in self.cart:
                self.cursor.execute('''
                    UPDATE books SET stock = stock - ? WHERE isbn = ?
                ''', (item['quantity'], item['isbn']))
            
            self.conn.commit()
            
            # Sync to Firebase
            firebase_data = {
                'sale_id': sale_id,
                'total_amount': self.cart_total,
                'payment_method': payment_method,
                'items': self.cart,
                'timestamp': sale_date
            }
            self.sync_to_firebase('sale', firebase_data)
            
            # Generate and save receipt
            receipt_path = self.save_receipt(sale_id, sale_date, payment_method, amount_paid, change)
            
            # Show success message with change
            success_msg = f"Sale completed successfully!\n\n"
            success_msg += f"Sale ID: {sale_id}\n"
            success_msg += f"Total: KES {self.cart_total:.2f}\n"
            success_msg += f"Paid: KES {amount_paid:.2f}\n"
            success_msg += f"Change: KES {change:.2f}\n"
            
            if self.firebase_connected:
                success_msg += f"\n✅ Data synced to cloud dashboard"
            
            success_msg += f"\nReceipt saved to:\n{receipt_path}"
            
            messagebox.showinfo("Success", success_msg)
            
            # Clear cart and reset form
            self.cart = []
            self.update_cart_display()
            self.amount_paid_entry.delete(0, 'end')
            self.change_label.config(text="KES 0.00", fg="#4CAF50")
            
            # Refresh inventory
            self.refresh_inventory()
            
        except Exception as e:
            self.conn.rollback()
            messagebox.showerror("Error", f"Failed to complete sale: {str(e)}")

    # ... (ALL YOUR EXISTING METHODS REMAIN EXACTLY THE SAME)
    # The rest of your code (search_book, add_to_cart, update_cart_display, etc.)
    # stays completely unchanged - just copy and paste them here

    def add_book(self):
        """Add new book to inventory and sync to Firebase"""
        try:
            isbn = self.inventory_entries['isbn'].get().strip()
            title = self.inventory_entries['title'].get().strip()
            author = self.inventory_entries['author'].get().strip()
            category = self.inventory_entries['category'].get().strip()
            price = float(self.inventory_entries['price'].get().strip())
            stock = int(self.inventory_entries['stock'].get().strip())
            
            if not isbn or not title:
                messagebox.showwarning("Input Error", "ISBN and Title are required")
                return
            
            self.cursor.execute('''
                INSERT INTO books (isbn, title, author, category, price, stock, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (isbn, title, author, category, price, stock, datetime.now().strftime('%Y-%m-%d')))
            
            self.conn.commit()
            
            # Sync to Firebase
            if self.firebase_connected:
                inventory_data = {
                    'item_id': isbn,
                    'title': title,
                    'stock_change': stock,
                    'new_stock': stock,
                    'action': 'added',
                    'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                }
                self.sync_to_firebase('inventory_update', inventory_data)
            
            messagebox.showinfo("Success", "Book added successfully!")
            self.refresh_inventory()
            self.clear_inventory_form()
            
        except ValueError:
            messagebox.showerror("Input Error", "Please enter valid price and stock values")
        except sqlite3.IntegrityError:
            messagebox.showerror("Input Error", "ISBN already exists in database")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add book: {str(e)}")

# The rest of your existing methods continue here...
# Just make sure to include ALL your original methods

# Main application
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = BookshopPOS(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        messagebox.showerror("Startup Error", f"Failed to start application: {str(e)}")
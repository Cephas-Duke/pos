import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import sqlite3
from datetime import datetime
import json
import os
import requests
import threading
import win32print # Required for printing

# ==========================================
# CONFIGURATION
# ==========================================
# YOUR EXACT PRINTER NAME
PRINTER_NAME = "BTP-R880NP(U) 1" 
# ==========================================

class BookshopPOS:
    def __init__(self, root):
        self.root = root
        self.root.title("HERIWADI BOOKSHOP - POS System")
        self.root.geometry("1200x700")
        self.root.configure(bg="#f0f0f0")
        
        # Firebase configuration (Using API Key for POS REST Access)
        self.firebase_config = {
            'apiKey': "AIzaSyCcQMjq4OwxondM8kjKgK4xitjk6QLsdg0",
            'databaseURL': "https://heriwadi-bookshop-default-rtdb.firebaseio.com",
            'projectId': "heriwadi-bookshop",
            'storageBucket': "heriwadi-bookshop.firebasestorage.app",
            'messagingSenderId': "1009993842704",
            'appId': "1:1009993842704:web:c308ea85000df2f72eca95"
        }
        
        # Initialize database
        self.init_database()
        self.init_firebase()
        
        # Cart items
        self.cart = []
        self.cart_total = 0.0
        
        # Create UI
        self.create_ui()
        
        # Load books
        self.refresh_inventory()
        
        print("HERIWADI BOOKSHOP POS System started successfully!")
        if self.firebase_connected:
            print("✅ Firebase connection ready")
        else:
            print("⚠️  Firebase not connected - running in offline mode")

    def init_database(self):
        """Initialize SQLite database"""
        self.conn = sqlite3.connect('bookshop.db')
        self.cursor = self.conn.cursor()
        
        # Create books table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                isbn TEXT UNIQUE,
                title TEXT NOT NULL,
                author TEXT,
                category TEXT,
                price REAL NOT NULL,
                stock INTEGER NOT NULL,
                date_added TEXT
            )
        ''')
        
        # Create sales table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS sales (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                sale_date TEXT NOT NULL,
                total_amount REAL NOT NULL,
                payment_method TEXT,
                items_json TEXT
            )
        ''')
        
        self.conn.commit()
        print("✅ Database initialized")

    def init_firebase(self):
        """Initialize Firebase connection"""
        try:
            if (self.firebase_config['databaseURL'] and 
                self.firebase_config['apiKey']):
                
                self.firebase_connected = True
                print(f"✅ Connected to Firebase: {self.firebase_config['databaseURL']}")
            else:
                self.firebase_connected = False
                print("❌ Invalid Firebase configuration")
                
        except Exception as e:
            print(f"Firebase initialization error: {e}")
            self.firebase_connected = False

    def create_ui(self):
        """Create the user interface"""
        # Create notebook (tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Create tabs
        self.create_sales_tab()
        self.create_inventory_tab()
        self.create_reports_tab()

    def create_sales_tab(self):
        """Create the sales/POS tab"""
        sales_frame = ttk.Frame(self.notebook)
        self.notebook.add(sales_frame, text="Sales / POS")
        
        # Left side - Product search and cart
        left_frame = ttk.Frame(sales_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        
        # Search section
        search_frame = ttk.LabelFrame(left_frame, text="Search Book", padding=10)
        search_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(search_frame, text="ISBN or Title:").pack(side='left', padx=5)
        self.search_entry = ttk.Entry(search_frame, width=30)
        self.search_entry.pack(side='left', padx=5)
        self.search_entry.bind('<Return>', lambda e: self.search_book())
        
        ttk.Button(search_frame, text="Search", command=self.search_book).pack(side='left', padx=5)
        
        # Search results
        self.search_results_frame = ttk.LabelFrame(left_frame, text="Search Results", padding=10)
        self.search_results_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        self.search_tree = ttk.Treeview(self.search_results_frame, 
                                        columns=('ISBN', 'Title', 'Author', 'Price', 'Stock'),
                                        show='headings', height=8)
        
        self.search_tree.heading('ISBN', text='ISBN')
        self.search_tree.heading('Title', text='Title')
        self.search_tree.heading('Author', text='Author')
        self.search_tree.heading('Price', text='Price')
        self.search_tree.heading('Stock', text='Stock')
        
        self.search_tree.column('ISBN', width=100)
        self.search_tree.column('Title', width=200)
        self.search_tree.column('Author', width=150)
        self.search_tree.column('Price', width=80)
        self.search_tree.column('Stock', width=60)
        
        self.search_tree.pack(fill='both', expand=True)
        self.search_tree.bind('<Double-1>', lambda e: self.add_to_cart())
        
        ttk.Button(left_frame, text="Add to Cart", command=self.add_to_cart).pack(pady=5)
        
        # Right side - Cart and payment
        right_frame = ttk.Frame(sales_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=10, pady=10)
        
        # Cart
        cart_frame = ttk.LabelFrame(right_frame, text="Shopping Cart", padding=10)
        cart_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        self.cart_text = scrolledtext.ScrolledText(cart_frame, height=15, width=50)
        self.cart_text.pack(fill='both', expand=True)
        
        # Total
        total_frame = ttk.Frame(right_frame)
        total_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(total_frame, text="TOTAL:", font=('Arial', 14, 'bold')).pack(side='left', padx=5)
        self.total_label = ttk.Label(total_frame, text="KES 0.00", 
                                     font=('Arial', 16, 'bold'), foreground='green')
        self.total_label.pack(side='left', padx=5)
        
        # Payment section
        payment_frame = ttk.LabelFrame(right_frame, text="Payment", padding=10)
        payment_frame.pack(fill='x')
        
        ttk.Label(payment_frame, text="Payment Method:").grid(row=0, column=0, sticky='w', pady=5)
        self.payment_var = tk.StringVar(value="Cash")
        payment_combo = ttk.Combobox(payment_frame, textvariable=self.payment_var,
                                     values=["Cash", "M-Pesa", "Card"], state='readonly', width=20)
        payment_combo.grid(row=0, column=1, pady=5)
        
        ttk.Label(payment_frame, text="Amount Paid:").grid(row=1, column=0, sticky='w', pady=5)
        self.amount_paid_entry = ttk.Entry(payment_frame, width=22)
        self.amount_paid_entry.grid(row=1, column=1, pady=5)
        self.amount_paid_entry.bind('<KeyRelease>', self.calculate_change)
        
        ttk.Label(payment_frame, text="Change:").grid(row=2, column=0, sticky='w', pady=5)
        self.change_label = ttk.Label(payment_frame, text="KES 0.00", 
                                      font=('Arial', 12, 'bold'), foreground='#4CAF50')
        self.change_label.grid(row=2, column=1, sticky='w', pady=5)
        
        # Buttons
        button_frame = ttk.Frame(right_frame)
        button_frame.pack(fill='x', pady=10)
        
        ttk.Button(button_frame, text="Complete Sale", 
                   command=self.complete_sale).pack(side='left', padx=5, fill='x', expand=True)
        ttk.Button(button_frame, text="Clear Cart", 
                   command=self.clear_cart).pack(side='left', padx=5, fill='x', expand=True)

    def create_inventory_tab(self):
        """Create inventory management tab"""
        inventory_frame = ttk.Frame(self.notebook)
        self.notebook.add(inventory_frame, text="Inventory")
        
        # Form for adding books
        form_frame = ttk.LabelFrame(inventory_frame, text="Add/Edit Book", padding=10)
        form_frame.pack(fill='x', padx=10, pady=10)
        
        self.inventory_entries = {}
        fields = [
            ('ISBN', 'isbn'),
            ('Title', 'title'),
            ('Author', 'author'),
            ('Category', 'category'),
            ('Price (KES)', 'price'),
            ('Stock', 'stock')
        ]
        
        for i, (label, key) in enumerate(fields):
            ttk.Label(form_frame, text=f"{label}:").grid(row=i//2, column=(i%2)*2, 
                                                        sticky='w', padx=5, pady=5)
            entry = ttk.Entry(form_frame, width=25)
            entry.grid(row=i//2, column=(i%2)*2+1, padx=5, pady=5)
            self.inventory_entries[key] = entry
        
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=3, column=0, columnspan=4, pady=10)
        
        ttk.Button(button_frame, text="Add Book", command=self.add_book).pack(side='left', padx=5)
        ttk.Button(button_frame, text="Clear Form", 
                   command=self.clear_inventory_form).pack(side='left', padx=5)
        
        # Inventory list
        list_frame = ttk.LabelFrame(inventory_frame, text="Current Inventory", padding=10)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.inventory_tree = ttk.Treeview(list_frame,
                                           columns=('ISBN', 'Title', 'Author', 'Category', 
                                                    'Price', 'Stock'),
                                           show='headings')
        
        for col in ('ISBN', 'Title', 'Author', 'Category', 'Price', 'Stock'):
            self.inventory_tree.heading(col, text=col)
            self.inventory_tree.column(col, width=100 if col != 'Title' else 200)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', 
                                  command=self.inventory_tree.yview)
        self.inventory_tree.configure(yscrollcommand=scrollbar.set)
        
        self.inventory_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')

    def create_reports_tab(self):
        """Create reports tab"""
        reports_frame = ttk.Frame(self.notebook)
        self.notebook.add(reports_frame, text="Reports")
        
        ttk.Label(reports_frame, text="Sales Reports", 
                  font=('Arial', 16, 'bold')).pack(pady=20)
        
        self.reports_text = scrolledtext.ScrolledText(reports_frame, height=20)
        self.reports_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        ttk.Button(reports_frame, text="Generate Report", 
                   command=self.generate_report).pack(pady=10)

    def search_book(self):
        """Search for books"""
        query = self.search_entry.get().strip()
        if not query:
            return
        
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
        
        self.cursor.execute('''
            SELECT isbn, title, author, price, stock 
            FROM books 
            WHERE isbn LIKE ? OR title LIKE ? OR author LIKE ?
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
        
        results = self.cursor.fetchall()
        
        for row in results:
            self.search_tree.insert('', 'end', values=row)
        
        if not results:
            messagebox.showinfo("No Results", "No books found matching your search")

    def add_to_cart(self):
        """Add selected book to cart"""
        selection = self.search_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select a book to add")
            return
        
        item = self.search_tree.item(selection[0])
        values = item['values']
        
        isbn, title, author, price, stock = values
        
        if stock <= 0:
            messagebox.showwarning("Out of Stock", f"{title} is out of stock")
            return
        
        quantity = simpledialog.askinteger(
            "Enter Quantity",
            f"Book: {title}\nPrice: KES {price}\nAvailable: {stock}\n\nEnter quantity:",
            parent=self.root,
            minvalue=1,
            maxvalue=stock,
            initialvalue=1
        )
        
        if quantity is None:
            return
        
        self.cart.append({
            'isbn': isbn,
            'title': title,
            'author': author,
            'price': float(price),
            'quantity': quantity
        })
        
        self.update_cart_display()
        messagebox.showinfo("Success", f"Added {quantity} x {title} to cart!")

    def update_cart_display(self):
        """Update cart display"""
        self.cart_text.delete('1.0', 'end')
        self.cart_total = 0.0
        
        for i, item in enumerate(self.cart, 1):
            subtotal = item['price'] * item['quantity']
            self.cart_total += subtotal
            
            line = f"{i}. {item['title']}\n"
            line += f"   Price: KES {item['price']:.2f} x {item['quantity']} = KES {subtotal:.2f}\n\n"
            self.cart_text.insert('end', line)
        
        self.total_label.config(text=f"KES {self.cart_total:.2f}")
        self.calculate_change()

    def calculate_change(self, event=None):
        """Calculate change"""
        try:
            amount_paid = float(self.amount_paid_entry.get() or 0)
            change = amount_paid - self.cart_total
            
            if change >= 0:
                self.change_label.config(text=f"KES {change:.2f}", foreground='#4CAF50')
            else:
                self.change_label.config(text=f"KES {change:.2f}", foreground='red')
        except ValueError:
            self.change_label.config(text="KES 0.00", foreground='#4CAF50')

    def complete_sale(self):
        """Complete the sale and sync to Firebase"""
        if not self.cart:
            messagebox.showwarning("Empty Cart", "Please add items to cart")
            return
        
        try:
            amount_paid = float(self.amount_paid_entry.get() or 0)
            
            if amount_paid < self.cart_total:
                messagebox.showerror("Insufficient Payment",
                                   f"Amount paid (KES {amount_paid:.2f}) is less than total (KES {self.cart_total:.2f})")
                return
            
            change = amount_paid - self.cart_total
            
            # --- 1. LOCAL DATABASE SAVE ---
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
            
            # --- 2. FIREBASE SYNC (In background thread) ---
            firebase_data = {
                'sale_id': sale_id,
                'total_amount': self.cart_total,
                'payment_method': payment_method,
                'items': self.cart,
                'timestamp': datetime.now().isoformat()
            }
            # Start sync in a separate thread
            threading.Thread(target=self.sync_sale, args=(firebase_data,), daemon=True).start()
            
            # --- 3. PRINTING LOGIC ---
            receipt_path = self.save_receipt_to_file(sale_id, sale_date, payment_method, 
                                             amount_paid, change)
            
            print_status = self.print_receipt_to_hardware(sale_id, sale_date, payment_method, amount_paid, change)
            
            # Success message
            success_msg = f"Sale completed successfully!\n\n"
            success_msg += f"Sale ID: {sale_id}\n"
            success_msg += f"Total: KES {self.cart_total:.2f}\n"
            success_msg += f"Change: KES {change:.2f}\n"
            
            if print_status:
                success_msg += "\n🖨️  Receipt Printed Successfully"
            else:
                success_msg += "\n⚠️ Printer Error - Check Connection"

            messagebox.showinfo("Success", success_msg)
            
            # Clear cart and refresh inventory
            self.clear_cart()
            self.refresh_inventory()
            
        except ValueError:
            messagebox.showerror("Invalid Amount", "Please enter a valid payment amount")
        except Exception as e:
            self.conn.rollback()
            messagebox.showerror("Error", f"Sale failed: {str(e)}")
            
    # NOTE: The sync and summary functions are moved outside the complete_sale method
    # and placed at the same indentation level as other class methods.
    
    def sync_sale(self, data):
        """Sync a single sale and update the daily summary."""
        if not self.firebase_connected:
            print("⚠️ Firebase not connected - skipping sync")
            return

        try:
            # 1. Sync Sale Record
            sale_id = data['sale_id']
            # Use .json endpoint for Firebase REST API
            url = f"{self.firebase_config['databaseURL']}/sales/{sale_id}.json"
            
            # Add authentication parameter
            params = {'auth': self.firebase_config['apiKey']}
            
            # Send data
            response = requests.put(url, json=data, params=params, timeout=10)
            
            if response.status_code == 200:
                print(f"✅ Sale {sale_id} synced to Firebase")
                # 2. Update Summary
                self.update_sales_summary(data)
            else:
                print(f"❌ Firebase sale sync failed: {response.status_code}. Response: {response.text}")
                    
        except requests.exceptions.Timeout:
            print("❌ Firebase sync timeout - check internet connection")
        except requests.exceptions.RequestException as e:
            print(f"❌ Firebase sync error: {e}")
        except Exception as e:
            print(f"❌ Unexpected sync error: {e}")

    def update_sales_summary(self, sale_data):
        """Update daily sales summary with better error handling."""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            url = f"{self.firebase_config['databaseURL']}/daily_sales/{today}.json"
            params = {'auth': self.firebase_config['apiKey']}
            
            # Get current summary
            response = requests.get(url, params=params, timeout=10)
            current = response.json() or {'total_sales': 0, 'transaction_count': 0}
            
            # Update summary
            updated = {
                'total_sales': current.get('total_sales', 0) + sale_data['total_amount'],
                'transaction_count': current.get('transaction_count', 0) + 1,
                'last_updated': datetime.now().isoformat()
            }
            
            # Save updated summary
            response = requests.put(url, json=updated, params=params, timeout=10)
            
            if response.status_code == 200:
                print(f"✅ Daily summary updated: {updated}")
            else:
                print(f"❌ Summary update failed: {response.text}")
                
        except Exception as e:
            print(f"❌ Summary update error: {e}")


    def print_receipt_to_hardware(self, sale_id, sale_date, payment_method, amount_paid, change):
        """Send receipt data directly to the Windows Printer"""
        try:
            # ESC/POS Commands
            ESC = b'\x1b'
            GS = b'\x1d'
            
            # Initialize
            raw_data = ESC + b'@' 
            
            # Align Center
            raw_data += ESC + b'a' + b'\x01'
            
            # Title (Bold + Double Height)
            # FIX: We use a string and encode it, rather than encoding bytes
            raw_data += ESC + b'!' + b'\x10' + "HERIWADI BOOKSHOP\n".encode('utf-8')
            raw_data += ESC + b'!' + b'\x00' # Reset font
            
            # Header info
            header = (
                "OLEKASI Along Maasai Lodge\n"
                "Rimpa Road\n"
                "Tel: 0723322449\n"
                "--------------------------------\n"
            )
            raw_data += header.encode('utf-8')
            
            # Align Left for items
            raw_data += ESC + b'a' + b'\x00'
            
            # Transaction Details
            details = (
                f"Receipt #: {sale_id}\n"
                f"Date: {sale_date}\n"
                "--------------------------------\n"
            )
            raw_data += details.encode('utf-8')
            
            # Items
            for item in self.cart:
                # Truncate title if too long to fit on one line
                title = item['title'][:20] 
                line = f"{title}\n"
                line += f"{item['quantity']} x {item['price']:.0f}         {item['price']*item['quantity']:.0f}\n"
                raw_data += line.encode('utf-8')
            
            raw_data += b'--------------------------------\n'
            
            # Totals (Align Right)
            raw_data += ESC + b'a' + b'\x02'
            totals = (
                f"TOTAL: KES {self.cart_total:.2f}\n"
                f"PAID:  KES {amount_paid:.2f}\n"
                f"CHANGE: KES {change:.2f}\n"
            )
            raw_data += totals.encode('utf-8')
            
            # Footer (Align Center)
            raw_data += ESC + b'a' + b'\x01'
            footer = (
                "--------------------------------\n"
                "Thank you for your business!\n"
            )
            raw_data += footer.encode('utf-8')
            
            # Feed paper (4 lines)
            raw_data += b'\n\n\n\n'
            
            # CUT PAPER COMMAND (GS V m)
            raw_data += GS + b'V' + b'\x42' + b'\x00'

            # Send to printer using win32print
            hPrinter = win32print.OpenPrinter(PRINTER_NAME)
            try:
                hJob = win32print.StartDocPrinter(hPrinter, 1, ("POS Receipt", None, "RAW"))
                try:
                    win32print.StartPagePrinter(hPrinter)
                    win32print.WritePrinter(hPrinter, raw_data)
                    win32print.EndPagePrinter(hPrinter)
                finally:
                    win32print.EndDocPrinter(hPrinter)
            finally:
                win32print.ClosePrinter(hPrinter)
                
            return True

        except Exception as e:
            print(f"Printing failed: {e}")
            return False

    def save_receipt_to_file(self, sale_id, sale_date, payment_method, amount_paid, change):
        """Save receipt to file (Backup)"""
        if not os.path.exists('receipts'):
            os.makedirs('receipts')
        
        filename = f"receipts/receipt_{sale_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        with open(filename, 'w') as f:
            f.write("="*50 + "\n")
            f.write("        HERIWADI BOOKSHOP\n")
            f.write("OLEKASI Along Maasai Lodge - Rimpa Road\n")
            f.write("          Tel: 0723322449\n")
            f.write("="*50 + "\n\n")
            f.write(f"Receipt #: {sale_id}\n")
            f.write(f"Date: {sale_date}\n")
            f.write(f"Payment: {payment_method}\n")
            f.write("-"*50 + "\n\n")
            
            for item in self.cart:
                f.write(f"{item['title']}\n")
                f.write(f"  {item['quantity']} x KES {item['price']:.2f} = KES {item['price']*item['quantity']:.2f}\n\n")
            
            f.write("-"*50 + "\n")
            f.write(f"TOTAL:         KES {self.cart_total:.2f}\n")
            f.write(f"PAID:          KES {amount_paid:.2f}\n")
            f.write(f"CHANGE:        KES {change:.2f}\n")
            f.write("="*50 + "\n")
            f.write("      Thank you for your business!\n")
            f.write("="*50 + "\n")
        
        return filename

    def clear_cart(self):
        """Clear shopping cart"""
        self.cart = []
        self.update_cart_display()
        self.amount_paid_entry.delete(0, 'end')

    def add_book(self):
        """Add new book to inventory"""
        try:
            isbn = self.inventory_entries['isbn'].get().strip()
            title = self.inventory_entries['title'].get().strip()
            author = self.inventory_entries['author'].get().strip()
            category = self.inventory_entries['category'].get().strip()
            price = float(self.inventory_entries['price'].get().strip())
            stock = int(self.inventory_entries['stock'].get().strip())
            
            if not isbn or not title:
                messagebox.showwarning("Input Error", "ISBN and Title required")
                return
            
            self.cursor.execute('''
                INSERT INTO books (isbn, title, author, category, price, stock, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (isbn, title, author, category, price, stock, 
                  datetime.now().strftime('%Y-%m-%d')))
            
            self.conn.commit()
            messagebox.showinfo("Success", "Book added successfully!")
            self.refresh_inventory()
            self.clear_inventory_form()
            
        except ValueError:
            messagebox.showerror("Input Error", "Invalid price or stock value")
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "ISBN already exists")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add book: {str(e)}")

    def clear_inventory_form(self):
        """Clear inventory form"""
        for entry in self.inventory_entries.values():
            entry.delete(0, 'end')

    def refresh_inventory(self):
        """Refresh inventory display"""
        for item in self.inventory_tree.get_children():
            self.inventory_tree.delete(item)
        
        self.cursor.execute('SELECT isbn, title, author, category, price, stock FROM books')
        
        for row in self.cursor.fetchall():
            self.inventory_tree.insert('', 'end', values=row)

    def generate_report(self):
        """Generate sales report"""
        self.reports_text.delete('1.0', 'end')
        
        # Get today's sales
        today = datetime.now().strftime('%Y-%m-%d')
        self.cursor.execute('''
            SELECT COUNT(*), SUM(total_amount)
            FROM sales
            WHERE DATE(sale_date) = ?
        ''', (today,))
        
        today_count, today_total = self.cursor.fetchone()
        today_total = today_total or 0
        
        # Get all-time sales
        self.cursor.execute('SELECT COUNT(*), SUM(total_amount) FROM sales')
        total_count, total_sales = self.cursor.fetchone()
        total_sales = total_sales or 0
        
        report = f"""
        ====================================
              HERIWADI BOOKSHOP
              SALES REPORT
        ====================================
        
        TODAY'S SALES ({today}):
        Transactions: {today_count or 0}
        Total: KES {today_total:.2f}
        
        ALL-TIME SALES:
        Total Transactions: {total_count or 0}
        Total Revenue: KES {total_sales:.2f}
        
        ====================================
        Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        ====================================
        """
        
        self.reports_text.insert('1.0', report)

    def __del__(self):
        """Cleanup"""
        if hasattr(self, 'conn'):
            self.conn.close()

# Main application
if __name__ == "__main__":
    try:
        root = tk.Tk()
        app = BookshopPOS(root)
        root.mainloop()
    except Exception as e:
        print(f"Application error: {e}")
        import traceback
        traceback.print_exc()
        input("Press Enter to close...")

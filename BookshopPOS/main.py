import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import sqlite3
from datetime import datetime, timedelta
import json
import os
import requests
import threading
# import win32print # The import is now handled conditionally within complete_sale

# ==========================================
# CONFIGURATION
# ==========================================
# YOUR EXACT PRINTER NAME
PRINTER_NAME = "BTP-R880NP(U) 1" 
# ==========================================

class BookshopPOS:
    def __init__(self, root):
        self.root = root
        self.root.title("HERIWADI BOOKSHOP - POS System (Enhanced)")
        self.root.geometry("1400x800")
        self.root.configure(bg="#f0f0f0")
        
        # Firebase configuration
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
        
        # Load inventory
        self.refresh_inventory()
        
        print("HERIWADI BOOKSHOP POS System started successfully!")
        if self.firebase_connected:
            print("✅ Firebase connection ready")
        else:
            print("⚠️ Firebase not connected - running in offline mode")

    def init_database(self):
        """Initialize SQLite database, updated for general inventory"""
        self.conn = sqlite3.connect('bookshop.db')
        self.cursor = self.conn.cursor()
        
        # Create inventory table (generalized from 'books')
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS inventory_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_code TEXT UNIQUE,
                title TEXT NOT NULL,
                author_or_supplier TEXT,
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
        print("✅ Database initialized (using inventory_items table)")

    def init_firebase(self):
        """Initialize Firebase connection"""
        try:
            if (self.firebase_config['databaseURL'] and 
                self.firebase_config['apiKey']):
                
                self.firebase_connected = True
            else:
                self.firebase_connected = False
                
        except Exception as e:
            print(f"Firebase initialization error: {e}")
            self.firebase_connected = False
            
    # --- UI Creation ---

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
        self.notebook.add(sales_frame, text="💰 Sales / POS")
        
        # Left side - Product search and cart
        left_frame = ttk.Frame(sales_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        
        # Search section
        search_frame = ttk.LabelFrame(left_frame, text="Search Item", padding=10)
        search_frame.pack(fill='x', pady=(0, 10))
        
        ttk.Label(search_frame, text="Code or Title:").pack(side='left', padx=5)
        self.search_entry = ttk.Entry(search_frame, width=30)
        self.search_entry.pack(side='left', padx=5)
        self.search_entry.bind('<Return>', lambda e: self.search_item())
        
        ttk.Button(search_frame, text="Search", command=self.search_item).pack(side='left', padx=5)
        
        # Search results
        self.search_results_frame = ttk.LabelFrame(left_frame, text="Search Results", padding=10)
        self.search_results_frame.pack(fill='both', expand=True, pady=(0, 10))
        
        self.search_tree = ttk.Treeview(self.search_results_frame, 
                                        columns=('Code', 'Title', 'Supplier', 'Price', 'Stock'),
                                        show='headings', height=8)
        
        self.search_tree.heading('Code', text='Item Code')
        self.search_tree.heading('Title', text='Title')
        self.search_tree.heading('Supplier', text='Author/Supplier')
        self.search_tree.heading('Price', text='Price')
        self.search_tree.heading('Stock', text='Stock')
        
        self.search_tree.column('Code', width=100)
        self.search_tree.column('Title', width=200)
        self.search_tree.column('Supplier', width=150)
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
        """Create enhanced inventory management tab"""
        inventory_frame = ttk.Frame(self.notebook)
        self.notebook.add(inventory_frame, text="📦 Inventory")
        
        # Form for adding/editing items
        form_frame = ttk.LabelFrame(inventory_frame, text="Add/Edit Item", padding=10)
        form_frame.pack(fill='x', padx=10, pady=10)
        
        self.inventory_entries = {}
        fields = [
            ('Item Code (ISBN/SKU)', 'item_code'), 
            ('Title/Description', 'title'),
            ('Author/Supplier', 'author_or_supplier'),
            ('Category', 'category'),
            ('Price (KES)', 'price'),
            ('Stock Quantity', 'stock')
        ]
        
        for i, (label, key) in enumerate(fields):
            ttk.Label(form_frame, text=f"{label}:").grid(row=i//2, column=(i%2)*2, 
                                                         sticky='w', padx=5, pady=5)
            entry = ttk.Entry(form_frame, width=30)
            entry.grid(row=i//2, column=(i%2)*2+1, padx=5, pady=5)
            self.inventory_entries[key] = entry
            
        button_frame = ttk.Frame(form_frame)
        button_frame.grid(row=3, column=0, columnspan=4, pady=10)
        
        self.add_button = ttk.Button(button_frame, text="Add Item", command=self.add_item)
        self.add_button.pack(side='left', padx=5)
        self.update_button = ttk.Button(button_frame, text="Update Stock", command=self.update_item_stock, state=tk.DISABLED)
        self.update_button.pack(side='left', padx=5)
        self.delete_button = ttk.Button(button_frame, text="Delete Item", command=self.delete_item, state=tk.DISABLED)
        self.delete_button.pack(side='left', padx=5)
        ttk.Button(button_frame, text="Clear Form", 
                   command=self.clear_inventory_form).pack(side='left', padx=5)
        
        # Inventory list
        list_frame = ttk.LabelFrame(inventory_frame, text="Current Inventory", padding=10)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        
        self.inventory_tree = ttk.Treeview(list_frame,
                                           columns=('Code', 'Title', 'Supplier', 'Category', 'Price', 'Stock'),
                                           show='headings')
        
        for col, display in [('Code', 'Item Code'), ('Title', 'Title/Description'), 
                             ('Supplier', 'Author/Supplier'), ('Category', 'Category'), 
                             ('Price', 'Price'), ('Stock', 'Stock')]:
            self.inventory_tree.heading(col, text=display)
            self.inventory_tree.column(col, width=100 if col != 'Title' else 200)
        
        scrollbar = ttk.Scrollbar(list_frame, orient='vertical', 
                                  command=self.inventory_tree.yview)
        self.inventory_tree.configure(yscrollcommand=scrollbar.set)
        
        self.inventory_tree.pack(side='left', fill='both', expand=True)
        scrollbar.pack(side='right', fill='y')
        
        # Bind double-click to load item for editing/updating
        self.inventory_tree.bind('<Double-1>', self.load_selected_item_for_edit)

    def create_reports_tab(self):
        """Create enhanced reports tab, including the clear display button."""
        reports_frame = ttk.Frame(self.notebook)
        self.notebook.add(reports_frame, text="📊 Reports")
        
        control_frame = ttk.LabelFrame(reports_frame, text="Report Controls", padding=10)
        control_frame.pack(fill='x', padx=10, pady=10)
        
        # Date selection for monthly report
        ttk.Label(control_frame, text="Select Month (YYYY-MM):").pack(side='left', padx=5)
        self.report_month_entry = ttk.Entry(control_frame, width=10)
        self.report_month_entry.insert(0, datetime.now().strftime('%Y-%m'))
        self.report_month_entry.pack(side='left', padx=5)

        ttk.Button(control_frame, text="Daily Sales Report", 
                   command=self.generate_daily_sales_report).pack(side='left', padx=10)
        ttk.Button(control_frame, text="Monthly Sales Report", 
                   command=self.generate_monthly_sales_report).pack(side='left', padx=10)
        ttk.Button(control_frame, text="Items Out of Stock", 
                   command=self.show_out_of_stock).pack(side='left', padx=10)
        
        # --- NEW: Clear Report Display Button ---
        ttk.Button(control_frame, text="Clear Display", 
                   command=self.clear_reports_display).pack(side='left', padx=20)

        self.reports_text = scrolledtext.ScrolledText(reports_frame, height=20, font=('Courier New', 10))
        self.reports_text.pack(fill='both', expand=True, padx=10, pady=10)
        
        # Initial report generation
        self.generate_daily_sales_report()
        
    # --- Sales Functions ---

    def search_item(self):
        """Search for items in the inventory"""
        query = self.search_entry.get().strip()
        if not query:
            self.refresh_inventory_search()
            return
        
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
        
        self.cursor.execute('''
            SELECT item_code, title, author_or_supplier, price, stock 
            FROM inventory_items 
            WHERE item_code LIKE ? OR title LIKE ? OR author_or_supplier LIKE ?
        ''', (f'%{query}%', f'%{query}%', f'%{query}%'))
        
        results = self.cursor.fetchall()
        
        for row in results:
            self.search_tree.insert('', 'end', values=row)
        
        if not results:
            messagebox.showinfo("No Results", "No items found matching your search")

    def refresh_inventory_search(self):
        """Populate the sales search results with all inventory items."""
        for item in self.search_tree.get_children():
            self.search_tree.delete(item)
            
        self.cursor.execute('SELECT item_code, title, author_or_supplier, price, stock FROM inventory_items')
        
        for row in self.cursor.fetchall():
            self.search_tree.insert('', 'end', values=row)

    def add_to_cart(self):
        """Add selected item to cart"""
        selection = self.search_tree.selection()
        if not selection:
            messagebox.showwarning("No Selection", "Please select an item to add")
            return
        
        item = self.search_tree.item(selection[0])
        values = item['values']
        
        item_code, title, author_or_supplier, price, stock = values
        
        if stock <= 0:
            messagebox.showwarning("Out of Stock", f"{title} is out of stock")
            return
        
        quantity = simpledialog.askinteger(
            "Enter Quantity",
            f"Item: {title}\nPrice: KES {price}\nAvailable: {stock}\n\nEnter quantity:",
            parent=self.root,
            minvalue=1,
            maxvalue=stock,
            initialvalue=1
        )
        
        if quantity is None:
            return
        
        self.cart.append({
            'item_code': item_code,
            'title': title,
            'price': float(price),
            'quantity': quantity
        })
        
        self.update_cart_display()
        messagebox.showinfo("Success", f"Added {quantity} x {title} to cart!")
        
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
        """Complete the sale and sync to Firebase (Updated printing check)"""
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
            
            # --- Database Transaction ---
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
                    UPDATE inventory_items SET stock = stock - ? WHERE item_code = ?
                ''', (item['quantity'], item['item_code']))
            
            self.conn.commit()
            
            # --- Printing Logic (FIXED/Improved Check) ---
            print_status = False
            try:
                import win32print
                print_status = self.print_receipt_to_hardware(sale_id, sale_date, payment_method, amount_paid, change)
            except ImportError:
                print("win32print module not found. Skipping hardware print.")
            except Exception as print_e:
                print(f"Hardware printing failed during execution: {print_e}")

            # --- Sync to Firebase ---
            firebase_data = {
                'sale_id': sale_id,
                'total_amount': self.cart_total,
                'payment_method': payment_method,
                'items': self.cart,
                'timestamp': datetime.now().isoformat()
            }
            self.sync_to_firebase('sale', firebase_data)
            self.save_receipt_to_file(sale_id, sale_date, payment_method, amount_paid, change)

            # Success message
            success_msg = f"Sale completed successfully!\n\n"
            success_msg += f"Sale ID: {sale_id}\n"
            success_msg += f"Total: KES {self.cart_total:.2f}\n"
            success_msg += f"Change: KES {change:.2f}\n"
            
            if print_status:
                success_msg += "\n🖨️ Receipt Printed Successfully"
            else:
                success_msg += "\n⚠️ Printer Error/Not Configured - Check Connection"

            messagebox.showinfo("Success", success_msg)
            
            # Clear cart and refresh
            self.clear_cart()
            self.refresh_inventory()
            self.refresh_inventory_search()
            
        except ValueError:
            messagebox.showerror("Invalid Amount", "Please enter a valid payment amount")
        except Exception as e:
            self.conn.rollback()
            messagebox.showerror("Error", f"Sale failed: {str(e)}")

    def print_receipt_to_hardware(self, sale_id, sale_date, payment_method, amount_paid, change):
        """Send receipt data directly to the Windows Printer"""
        # (Function kept as is, requires win32print and Windows environment)
        import win32print # Re-import inside function to ensure it's available
        try:
            # ESC/POS Commands
            ESC = b'\x1b'
            GS = b'\x1d'
            
            raw_data = ESC + b'@'
            raw_data += ESC + b'a' + b'\x01'
            raw_data += ESC + b'!' + b'\x10' + "HERIWADI BOOKSHOP\n".encode('utf-8')
            raw_data += ESC + b'!' + b'\x00'
            
            header = (
                "OLEKASI Along Maasai Lodge\n"
                "Rimpa Road\n"
                "Tel: 0723322449\n"
                "--------------------------------\n"
            )
            raw_data += header.encode('utf-8')
            
            raw_data += ESC + b'a' + b'\x00'
            
            details = (
                f"Receipt #: {sale_id}\n"
                f"Date: {sale_date}\n"
                "--------------------------------\n"
            )
            raw_data += details.encode('utf-8')
            
            # Items
            for item in self.cart:
                title = item['title'][:20]  
                line = f"{title}\n"
                line += f"{item['quantity']} x {item['price']:.0f}           {item['price']*item['quantity']:.0f}\n"
                raw_data += line.encode('utf-8')
            
            raw_data += b'--------------------------------\n'
            
            raw_data += ESC + b'a' + b'\x02'
            totals = (
                f"TOTAL: KES {self.cart_total:.2f}\n"
                f"PAID:  KES {amount_paid:.2f}\n"
                f"CHANGE: KES {change:.2f}\n"
            )
            raw_data += totals.encode('utf-8')
            
            raw_data += ESC + b'a' + b'\x01'
            footer = (
                "--------------------------------\n"
                "Thank you for your business!\n"
            )
            raw_data += footer.encode('utf-8')
            
            raw_data += b'\n\n\n\n'
            raw_data += GS + b'V' + b'\x42' + b'\x00'

            # Send to printer
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

    def update_cart_display(self):
        """Update cart display"""
        self.cart_text.delete('1.0', 'end')
        self.cart_total = 0.0
        
        for i, item in enumerate(self.cart, 1):
            subtotal = item['price'] * item['quantity']
            self.cart_total += subtotal
            
            line = f"{i}. {item['title']}\n"
            line += f"  Price: KES {item['price']:.2f} x {item['quantity']} = KES {subtotal:.2f}\n\n"
            self.cart_text.insert('end', line)
        
        self.total_label.config(text=f"KES {self.cart_total:.2f}")
        self.calculate_change()

    def clear_cart(self):
        """Clear shopping cart"""
        self.cart = []
        self.update_cart_display()
        self.amount_paid_entry.delete(0, 'end')

    # --- Inventory Functions ---

    def add_item(self):
        """Add new item to inventory"""
        try:
            item_code = self.inventory_entries['item_code'].get().strip()
            title = self.inventory_entries['title'].get().strip()
            author_or_supplier = self.inventory_entries['author_or_supplier'].get().strip()
            category = self.inventory_entries['category'].get().strip()
            price = float(self.inventory_entries['price'].get().strip())
            stock = int(self.inventory_entries['stock'].get().strip())
            
            if not item_code or not title:
                messagebox.showwarning("Input Error", "Item Code and Title required")
                return
            
            self.cursor.execute('''
                INSERT INTO inventory_items (item_code, title, author_or_supplier, category, price, stock, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (item_code, title, author_or_supplier, category, price, stock, 
                  datetime.now().strftime('%Y-%m-%d')))
            
            self.conn.commit()
            messagebox.showinfo("Success", "Item added successfully!")
            self.refresh_inventory()
            self.clear_inventory_form()
            
        except ValueError:
            messagebox.showerror("Input Error", "Invalid price or stock value")
        except sqlite3.IntegrityError:
            messagebox.showerror("Error", "Item Code already exists")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to add item: {str(e)}")

    def load_selected_item_for_edit(self, event):
        """Load selected item's details into the form for updating/deleting."""
        selection = self.inventory_tree.selection()
        if not selection:
            return

        item = self.inventory_tree.item(selection[0])
        values = item['values']
        
        keys = ['item_code', 'title', 'author_or_supplier', 'category', 'price', 'stock']
        
        self.clear_inventory_form()
        for key, value in zip(keys, values):
            entry = self.inventory_entries[key]
            entry.insert(0, str(value))
        
        self.inventory_entries['item_code'].config(state=tk.DISABLED)
        self.add_button.config(state=tk.DISABLED)
        self.update_button.config(state=tk.NORMAL)
        self.delete_button.config(state=tk.NORMAL)


    def update_item_stock(self):
        """Update existing item's details in inventory."""
        try:
            item_code = self.inventory_entries['item_code'].get().strip()
            title = self.inventory_entries['title'].get().strip()
            author_or_supplier = self.inventory_entries['author_or_supplier'].get().strip()
            category = self.inventory_entries['category'].get().strip()
            price = float(self.inventory_entries['price'].get().strip())
            stock = int(self.inventory_entries['stock'].get().strip())
            
            if not item_code:
                messagebox.showwarning("Selection Error", "No item selected for update.")
                return

            self.cursor.execute('''
                UPDATE inventory_items 
                SET title = ?, author_or_supplier = ?, category = ?, price = ?, stock = ? 
                WHERE item_code = ?
            ''', (title, author_or_supplier, category, price, stock, item_code))
            
            self.conn.commit()
            messagebox.showinfo("Success", f"Item {item_code} updated successfully!")
            self.refresh_inventory()
            self.clear_inventory_form()

        except ValueError:
            messagebox.showerror("Input Error", "Invalid price or stock value")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to update item: {str(e)}")

    def delete_item(self):
        """Delete selected item from inventory."""
        item_code = self.inventory_entries['item_code'].get().strip()
        title = self.inventory_entries['title'].get().strip()

        if not item_code:
            messagebox.showwarning("Selection Error", "No item selected for deletion.")
            return

        if messagebox.askyesno("Confirm Deletion", f"Are you sure you want to delete item: {title} ({item_code})?"):
            try:
                self.cursor.execute('DELETE FROM inventory_items WHERE item_code = ?', (item_code,))
                self.conn.commit()
                messagebox.showinfo("Success", f"Item {item_code} deleted successfully!")
                self.refresh_inventory()
                self.clear_inventory_form()
            except Exception as e:
                messagebox.showerror("Error", f"Failed to delete item: {str(e)}")

    def clear_inventory_form(self):
        """Clear inventory form and reset buttons"""
        for entry in self.inventory_entries.values():
            entry.config(state=tk.NORMAL)
            entry.delete(0, 'end')
        
        self.add_button.config(state=tk.NORMAL)
        self.update_button.config(state=tk.DISABLED)
        self.delete_button.config(state=tk.DISABLED)

    def refresh_inventory(self):
        """Refresh inventory display on the Inventory tab"""
        for item in self.inventory_tree.get_children():
            self.inventory_tree.delete(item)
        
        self.cursor.execute('SELECT item_code, title, author_or_supplier, category, price, stock FROM inventory_items')
        
        for row in self.cursor.fetchall():
            self.inventory_tree.insert('', 'end', values=row)

    # --- Reporting Functions ---

    def clear_reports_display(self):
        """Clears the text area in the Reports tab."""
        self.reports_text.delete('1.0', 'end')
        self.reports_text.insert('1.0', "Report display cleared. Select a report to generate.")

    def generate_daily_sales_report(self):
        """Generate and display today's detailed sales report."""
        self.reports_text.delete('1.0', 'end')
        today = datetime.now().strftime('%Y-%m-%d')
        
        self.cursor.execute('''
            SELECT id, sale_date, total_amount, payment_method
            FROM sales
            WHERE DATE(sale_date) = ?
            ORDER BY sale_date DESC
        ''', (today,))
        
        sales_data = self.cursor.fetchall()
        
        report_title = f"DAILY SALES REPORT - {today}"
        self.reports_text.insert('1.0', "=" * len(report_title) + "\n")
        self.reports_text.insert('end', f"{report_title}\n")
        self.reports_text.insert('end', "=" * len(report_title) + "\n\n")
        
        if not sales_data:
            self.reports_text.insert('end', "No sales recorded for today.")
            return

        total_revenue = 0.0
        
        self.reports_text.insert('end', f"{'ID':<5}{'Time':<10}{'Total':>10}{'Method':>10}\n")
        self.reports_text.insert('end', "-" * 35 + "\n")
        
        for id, full_date, total, method in sales_data:
            sale_time = datetime.strptime(full_date, '%Y-%m-%d %H:%M:%S').strftime('%H:%M:%S')
            self.reports_text.insert('end', f"{id:<5}{sale_time:<10}{total:>10.2f}{method:>10}\n")
            total_revenue += total
            
        self.reports_text.insert('end', "-" * 35 + "\n")
        self.reports_text.insert('end', f"TOTAL TRANSACTIONS: {len(sales_data)}\n")
        self.reports_text.insert('end', f"TOTAL REVENUE: KES {total_revenue:.2f}\n")
        self.reports_text.insert('end', "=" * 35 + "\n")


    def generate_monthly_sales_report(self):
        """Generate and display monthly detailed sales report."""
        self.reports_text.delete('1.0', 'end')
        month_str = self.report_month_entry.get().strip()
        
        try:
            # Validate format YYYY-MM
            datetime.strptime(month_str, '%Y-%m')
            start_date = f"{month_str}-01 00:00:00"
            
            year, month = map(int, month_str.split('-'))
            if month == 12:
                next_month_str = f"{year+1}-01"
            else:
                next_month_str = f"{year}-{month+1:02d}"
            end_date = f"{next_month_str}-01 00:00:00"

        except ValueError:
            messagebox.showerror("Input Error", "Please enter month in YYYY-MM format (e.g., 2025-11).")
            return
            
        self.cursor.execute('''
            SELECT id, sale_date, total_amount, payment_method
            FROM sales
            WHERE sale_date >= ? AND sale_date < ?
            ORDER BY sale_date DESC
        ''', (start_date, end_date))
        
        sales_data = self.cursor.fetchall()
        
        report_title = f"MONTHLY SALES REPORT - {month_str}"
        self.reports_text.insert('1.0', "=" * len(report_title) + "\n")
        self.reports_text.insert('end', f"{report_title}\n")
        self.reports_text.insert('end', "=" * len(report_title) + "\n\n")

        if not sales_data:
            self.reports_text.insert('end', f"No sales recorded for {month_str}.")
            return

        total_revenue = 0.0
        
        self.reports_text.insert('end', f"{'ID':<5}{'Date':<18}{'Total':>10}{'Method':>10}\n")
        self.reports_text.insert('end', "-" * 45 + "\n")
        
        for id, full_date, total, method in sales_data:
            self.reports_text.insert('end', f"{id:<5}{full_date:<18}{total:>10.2f}{method:>10}\n")
            total_revenue += total
            
        self.reports_text.insert('end', "-" * 45 + "\n")
        self.reports_text.insert('end', f"TOTAL TRANSACTIONS: {len(sales_data)}\n")
        self.reports_text.insert('end', f"TOTAL REVENUE: KES {total_revenue:.2f}\n")
        self.reports_text.insert('end', "=" * 45 + "\n")

    def show_out_of_stock(self):
        """Display a report of all items with stock <= 5."""
        self.reports_text.delete('1.0', 'end')
        
        self.cursor.execute('''
            SELECT item_code, title, category, stock 
            FROM inventory_items
            WHERE stock <= 5
            ORDER BY stock ASC, title ASC
        ''')
        
        out_of_stock_data = self.cursor.fetchall()

        report_title = "INVENTORY STOCK ALERT (Stock <= 5)"
        self.reports_text.insert('1.0', "=" * len(report_title) + "\n")
        self.reports_text.insert('end', f"{report_title}\n")
        self.reports_text.insert('end', "=" * len(report_title) + "\n\n")

        if not out_of_stock_data:
            self.reports_text.insert('end', "✅ All inventory items are well stocked (above 5 units).")
            return

        self.reports_text.insert('end', f"{'Code':<15}{'Title':<35}{'Category':<15}{'Stock':>10}\n")
        self.reports_text.insert('end', "-" * 75 + "\n")

        for code, title, category, stock in out_of_stock_data:
            # Truncate title for display
            display_title = title[:33] + '..' if len(title) > 35 else title
            self.reports_text.insert('end', f"{code:<15}{display_title:<35}{category:<15}{stock:>10}\n")

        self.reports_text.insert('end', "-" * 75 + "\n")
        self.reports_text.insert('end', f"TOTAL LOW STOCK ITEMS: {len(out_of_stock_data)}\n")
        self.reports_text.insert('end', "=" * 75 + "\n")
        
    # --- Firebase/Utility Functions ---

    def save_receipt_to_file(self, sale_id, sale_date, payment_method, amount_paid, change):
        """Save receipt to file (Backup)"""
        if not os.path.exists('receipts'):
            os.makedirs('receipts')
        
        filename = f"receipts/receipt_{sale_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
        
        with open(filename, 'w') as f:
            f.write("="*50 + "\n")
            f.write("        HERIWADI BOOKSHOP\n")
            f.write("OLEKASI Along Maasai Lodge - Rimpa Road\n")
            f.write("         Tel: 0723322449\n")
            f.write("="*50 + "\n\n")
            f.write(f"Receipt #: {sale_id}\n")
            f.write(f"Date: {sale_date}\n")
            f.write(f"Payment: {payment_method}\n")
            f.write("-"*50 + "\n\n")
            
            for item in self.cart:
                f.write(f"{item['title']}\n")
                f.write(f"  {item['quantity']} x KES {item['price']:.2f} = KES {item['price']*item['quantity']:.2f}\n\n")
            
            f.write("-"*50 + "\n")
            f.write(f"TOTAL:           KES {self.cart_total:.2f}\n")
            f.write(f"PAID:            KES {amount_paid:.2f}\n")
            f.write(f"CHANGE:          KES {change:.2f}\n")
            f.write("="*50 + "\n")
            f.write("      Thank you for your business!\n")
            f.write("="*50 + "\n")
        
        return filename

    def sync_to_firebase(self, data_type, data):
        """Sync data to Firebase"""
        if not self.firebase_connected:
            return
        
        def sync_thread():
            try:
                if data_type == 'sale':
                    url = f"{self.firebase_config['databaseURL']}/sales/{data['sale_id']}.json"
                    response = requests.put(url, json=data)
                    
                    if response.status_code == 200:
                        print(f"✅ Sale {data['sale_id']} synced to Firebase")
                        self.update_sales_summary(data)
                    else:
                        print(f"❌ Failed to sync: {response.text}")
                        
            except Exception as e:
                print(f"Firebase sync error: {e}")
        
        thread = threading.Thread(target=sync_thread)
        thread.daemon = True
        thread.start()

    def update_sales_summary(self, sale_data):
        """Update daily sales summary"""
        try:
            today = datetime.now().strftime('%Y-%m-%d')
            url = f"{self.firebase_config['databaseURL']}/daily_sales/{today}.json"
            
            response = requests.get(url)
            current = response.json() or {'total_sales': 0, 'transaction_count': 0}
            
            updated = {
                'total_sales': current.get('total_sales', 0) + sale_data['total_amount'],
                'transaction_count': current.get('transaction_count', 0) + 1,
                'last_updated': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            }
            
            requests.put(url, json=updated)
            print("✅ Daily summary updated")
            
        except Exception as e:
            print(f"Summary update error: {e}")

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
        # input("Press Enter to close...") # Uncomment this line if running locally for debugging exit

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import sqlite3
from datetime import datetime
import json
import os
import hashlib
import csv
import threading
import requests

# --- TRY IMPORTING PRINTER LIBRARIES ---
try:
    import win32print
    import win32ui
except ImportError:
    win32print = None
    print("⚠️ WARNING: 'pywin32' not installed. Printing will not work.")

# ==========================================
# CONFIGURATION
# ==========================================
PRINTER_NAME = "BTP-R880NP(U) 1"
# 👇 REPLACE WITH YOUR ACTUAL FIREBASE DB URL
FIREBASE_URL = "https://heriwadi-bookshop-default-rtdb.firebaseio.com"

# ==========================================
# DATABASE SETUP FUNCTION
# ==========================================
def initialize_database():
    conn = sqlite3.connect('bookshop.db')
    cursor = conn.cursor()
    
    # 1. Create Products Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS products (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sku TEXT UNIQUE, 
            title TEXT NOT NULL,
            author_supplier TEXT, 
            category TEXT,
            product_type TEXT NOT NULL DEFAULT 'Book', 
            price REAL NOT NULL,
            cost_price REAL DEFAULT 0.0, 
            stock INTEGER NOT NULL,
            date_added TEXT
        )
    ''')
    
    # 2. Create Sales Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS sales (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sale_date TEXT NOT NULL,
            total_amount REAL NOT NULL,
            discount REAL DEFAULT 0.0,
            total_profit REAL DEFAULT 0.0, 
            payment_method TEXT,
            items_json TEXT 
        )
    ''')
    
    # --- CHECK FOR NEW COLUMNS (MIGRATION) ---
    try:
        cursor.execute("SELECT discount FROM sales LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE sales ADD COLUMN discount REAL DEFAULT 0.0")

    try:
        cursor.execute("SELECT total_profit FROM sales LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE sales ADD COLUMN total_profit REAL DEFAULT 0.0")

    # 3. Create Users Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT,
            role TEXT
        )
    ''')
    
    # 4. Seed Default Users
    cursor.execute("SELECT count(*) FROM users")
    if cursor.fetchone()[0] == 0:
        # Default: admin/admin123 and user/user123
        admin_pw = hashlib.sha256("admin123".encode()).hexdigest()
        user_pw = hashlib.sha256("user123".encode()).hexdigest()
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("admin", admin_pw, "Director"))
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("user", user_pw, "Attendant"))
        
    conn.commit()
    conn.close()

# ==========================================
# LOGIN WINDOW
# ==========================================
class LoginWindow:
    def __init__(self, root, on_login_success):
        self.root = root
        self.on_login_success = on_login_success
        self.root.title("Login - HERIWADI BOOKSHOP")
        self.root.geometry("400x350")
        
        # UI Elements
        tk.Label(root, text="LOGIN", font=('Arial', 18, 'bold')).pack(pady=20)
        
        tk.Label(root, text="Username").pack()
        self.user_entry = tk.Entry(root, font=('Arial', 12))
        self.user_entry.pack(pady=5)
        
        tk.Label(root, text="Password").pack()
        self.pass_entry = tk.Entry(root, show="*", font=('Arial', 12))
        self.pass_entry.pack(pady=5)
        self.pass_entry.bind('<Return>', self.attempt_login)
        
        tk.Button(root, text="Login", command=self.attempt_login, bg="#4CAF50", fg="white", font=('Arial', 12), width=15).pack(pady=20)

    def attempt_login(self, event=None):
        username = self.user_entry.get().strip()
        password = self.pass_entry.get().strip()
        hashed_pw = hashlib.sha256(password.encode()).hexdigest()
        
        conn = sqlite3.connect('bookshop.db')
        cursor = conn.cursor()
        cursor.execute("SELECT role FROM users WHERE username=? AND password_hash=?", (username, hashed_pw))
        result = cursor.fetchone()
        conn.close()
        
        if result:
            role = result[0]
            # Clear login widgets
            for widget in self.root.winfo_children():
                widget.destroy()
            self.on_login_success(username, role)
        else:
            messagebox.showerror("Error", "Invalid Username or Password")

# ==========================================
# MAIN POS APPLICATION
# ==========================================
class BookshopPOS:
    def __init__(self, root, username, role):
        self.root = root
        self.current_user = username
        self.current_role = role 
        
        self.root.title(f"HERIWADI BOOKSHOP POS | User: {username} ({role})")
        self.root.geometry("1300x750")
        
        self.conn = sqlite3.connect('bookshop.db')
        self.cursor = self.conn.cursor()
        
        # Cart Variables
        self.cart = []
        self.subtotal = 0.0
        self.discount_amount = 0.0 # New variable for discount
        self.final_total = 0.0
        
        self.create_ui()
        
        # Initial Load & Sync
        self.refresh_inventory()
        # Start background sync
        threading.Thread(target=self.sync_inventory_from_firebase, daemon=True).start()

    def create_ui(self):
        # Tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True)
        
        self.create_sales_tab()
        self.create_inventory_tab()
        self.create_reports_tab()
        
        # Bind Tab Change to refresh
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)

    def on_tab_change(self, event):
        selected_tab = self.notebook.tab(self.notebook.select(), "text")
        if selected_tab == "Reports":
            self.generate_report()
        elif selected_tab == "Inventory Management":
            self.refresh_inventory()

    # =========================================================================
    # 🛒 SALES TAB (MODIFIED FOR DISCOUNT)
    # =========================================================================
    def create_sales_tab(self):
        sales_frame = tk.Frame(self.notebook)
        self.notebook.add(sales_frame, text="Sales Terminal")
        
        # LEFT SIDE: SEARCH & LIST
        left_frame = tk.Frame(sales_frame, padx=10, pady=10)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        # Search
        search_frame = tk.Frame(left_frame)
        search_frame.pack(fill=tk.X, pady=(0, 10))
        tk.Label(search_frame, text="Search (SKU/Title):").pack(side=tk.LEFT)
        self.search_entry = tk.Entry(search_frame, font=('Arial', 12))
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=5)
        self.search_entry.bind('<Return>', lambda e: self.search_product())
        tk.Button(search_frame, text="Search", command=self.search_product).pack(side=tk.LEFT)
        
        # Search Results List
        columns = ('SKU', 'Title', 'Price', 'Stock')
        self.search_tree = ttk.Treeview(left_frame, columns=columns, show='headings', height=15)
        for col in columns:
            self.search_tree.heading(col, text=col)
            self.search_tree.column(col, width=100)
        self.search_tree.column('Title', width=300)
        self.search_tree.pack(fill=tk.BOTH, expand=True)
        
        # Add to Cart Button
        tk.Button(left_frame, text="Add to Cart ➡", command=self.add_to_cart, bg="#2196F3", fg="white", font=('Arial', 12, 'bold')).pack(fill=tk.X, pady=10)

        # RIGHT SIDE: CART & PAYMENT
        right_frame = tk.Frame(sales_frame, padx=10, pady=10, bg="#f0f0f0", width=400)
        right_frame.pack(side=tk.RIGHT, fill=tk.Y)
        right_frame.pack_propagate(False)
        
        tk.Label(right_frame, text="CURRENT CART", bg="#f0f0f0", font=('Arial', 12, 'bold')).pack()
        
        self.cart_text = scrolledtext.ScrolledText(right_frame, height=15, width=40)
        self.cart_text.pack(pady=5)
        
        # --- NEW DISCOUNT BUTTON ---
        tk.Button(right_frame, text="✂ Apply Discount", command=self.prompt_discount, bg="orange", fg="black").pack(fill=tk.X, pady=5)
        
        # Totals
        self.total_label = tk.Label(right_frame, text="Total: KES 0.00", font=('Arial', 16, 'bold'), bg="#f0f0f0", fg="red")
        self.total_label.pack(pady=10)
        
        # Payment Input
        tk.Label(right_frame, text="Amount Paid:", bg="#f0f0f0").pack()
        self.amount_paid_entry = tk.Entry(right_frame, font=('Arial', 14))
        self.amount_paid_entry.pack(pady=5)
        self.amount_paid_entry.bind('<KeyRelease>', self.calculate_change)
        
        self.change_label = tk.Label(right_frame, text="Change: KES 0.00", font=('Arial', 12), bg="#f0f0f0")
        self.change_label.pack(pady=5)
        
        # Payment Method
        tk.Label(right_frame, text="Payment Method:", bg="#f0f0f0").pack()
        self.payment_var = tk.StringVar(value="Cash")
        ttk.Combobox(right_frame, textvariable=self.payment_var, values=["Cash", "M-Pesa", "Card"], state="readonly").pack(pady=5)
        
        # Buttons
        tk.Button(right_frame, text="COMPLETE SALE", command=self.complete_sale, bg="#4CAF50", fg="white", font=('Arial', 14, 'bold'), height=2).pack(fill=tk.X, pady=(20, 5))
        tk.Button(right_frame, text="Clear Cart", command=self.clear_cart, bg="#f44336", fg="white").pack(fill=tk.X)

    # =========================================================================
    # 📦 INVENTORY TAB
    # =========================================================================
    def create_inventory_tab(self):
        inv_frame = tk.Frame(self.notebook)
        self.notebook.add(inv_frame, text="Inventory Management")
        
        # Form
        form_frame = tk.LabelFrame(inv_frame, text="Product Details", padx=10, pady=10)
        form_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.inv_entries = {}
        fields = ['SKU', 'Title', 'Author/Supplier', 'Category', 'Product Type', 'Sell Price', 'Cost Price', 'Stock']
        
        # Grid layout for form
        for i, field in enumerate(fields):
            row = i // 4
            col = (i % 4) * 2
            
            # Helper for keys
            key = field.lower().replace(' ', '_').replace('/', '_')
            if field == 'Sell Price': key = 'price'
            if field == 'Author/Supplier': key = 'author_supplier'
            
            # Hide Cost Price for Attendant
            if key == 'cost_price' and self.current_role == "Attendant":
                continue
            
            tk.Label(form_frame, text=field).grid(row=row, column=col, sticky='e', padx=5, pady=5)
            
            if field == 'Product Type':
                entry = ttk.Combobox(form_frame, values=["Book", "Stationery", "Other"], state='readonly')
            else:
                entry = tk.Entry(form_frame)
                
            entry.grid(row=row, column=col+1, sticky='w', padx=5, pady=5)
            self.inv_entries[key] = entry

        # CRUD Buttons
        btn_frame = tk.Frame(form_frame)
        btn_frame.grid(row=2, column=0, columnspan=8, pady=10)
        
        tk.Button(btn_frame, text="New", command=self.reset_form_for_new).pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Add Product", command=self.add_product, bg="#2196F3", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Update Selected", command=self.update_product, bg="orange").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Delete Selected", command=self.delete_product, bg="red", fg="white").pack(side=tk.LEFT, padx=5)
        tk.Button(btn_frame, text="Sync from Cloud", command=lambda: threading.Thread(target=self.sync_inventory_from_firebase, daemon=True).start(), bg="purple", fg="white").pack(side=tk.LEFT, padx=5)

        # Inventory List
        cols = ('SKU', 'Title', 'Type', 'Price', 'Cost', 'Stock')
        self.inventory_tree = ttk.Treeview(inv_frame, columns=cols, show='headings')
        for c in cols:
            self.inventory_tree.heading(c, text=c)
            self.inventory_tree.column(c, width=80)
        self.inventory_tree.column('Title', width=200)
        
        # Hide cost column if attendant
        if self.current_role == "Attendant":
            self.inventory_tree.column('Cost', width=0, stretch=False)
            
        self.inventory_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        
        if self.current_role != "Attendant":
            self.inventory_tree.bind('<<TreeviewSelect>>', self.on_inventory_select)

    # =========================================================================
    # 📈 REPORTS TAB
    # =========================================================================
    def create_reports_tab(self):
        rep_frame = tk.Frame(self.notebook)
        self.notebook.add(rep_frame, text="Reports")
        
        # Controls
        ctrl_frame = tk.Frame(rep_frame, pady=10)
        ctrl_frame.pack(fill=tk.X)
        tk.Button(ctrl_frame, text="Refresh Reports", command=self.generate_report).pack(side=tk.LEFT, padx=10)
        
        if self.current_role == "Director":
            tk.Button(ctrl_frame, text="Export CSV", command=self.export_sales_to_csv).pack(side=tk.LEFT, padx=10)
            tk.Button(ctrl_frame, text="Delete Selected Sale", command=self.delete_sale_prompt, bg="red", fg="white").pack(side=tk.RIGHT, padx=10)

        # Summary Text
        self.reports_text = scrolledtext.ScrolledText(rep_frame, height=8)
        self.reports_text.pack(fill=tk.X, padx=10)
        
        # Sales List
        cols = ('ID', 'Total', 'Discount', 'Date')
        self.sales_tree = ttk.Treeview(rep_frame, columns=cols, show='headings')
        self.sales_tree.heading('ID', text='ID')
        self.sales_tree.heading('Total', text='Total Amount')
        self.sales_tree.heading('Discount', text='Discount')
        self.sales_tree.heading('Date', text='Date')
        self.sales_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

    # =========================================================================
    # LOGIC: SEARCH, CART, DISCOUNT, SALE
    # =========================================================================
    def search_product(self):
        query = self.search_entry.get().strip()
        self.search_tree.delete(*self.search_tree.get_children())
        
        sql = "SELECT sku, title, price, stock FROM products WHERE stock > 0"
        params = ()
        if query:
            sql += " AND (sku LIKE ? OR title LIKE ?)"
            params = (f'%{query}%', f'%{query}%')
            
        self.cursor.execute(sql, params)
        for row in self.cursor.fetchall():
            self.search_tree.insert('', 'end', values=row)

    def add_to_cart(self):
        selected_item = self.search_tree.selection()
        if not selected_item:
            return
        
        item_values = self.search_tree.item(selected_item[0])['values']
        sku, title, price, stock = item_values[0], item_values[1], float(item_values[2]), int(item_values[3])
        
        # Check if already in cart
        for item in self.cart:
            if item['sku'] == sku:
                if item['qty'] + 1 > stock:
                    messagebox.showwarning("Stock Limit", f"Only {stock} available!")
                    return
                item['qty'] += 1
                self.update_cart_display()
                return
        
        # Get cost price for profit calc
        self.cursor.execute("SELECT cost_price FROM products WHERE sku=?", (sku,))
        cost = self.cursor.fetchone()[0]
        
        self.cart.append({
            'sku': sku,
            'title': title,
            'price': price,
            'cost': cost,
            'qty': 1
        })
        self.update_cart_display()
        
        # Clear search for next item
        self.search_entry.delete(0, 'end')
        self.search_entry.focus()

    def prompt_discount(self):
        """Allows user to enter a discount amount"""
        if not self.cart:
            messagebox.showwarning("Empty Cart", "Add items before giving a discount.")
            return

        # Calculate raw subtotal first to prevent over-discounting
        raw_subtotal = sum(item['price'] * item['qty'] for item in self.cart)
        
        amount = simpledialog.askfloat("Input Discount", f"Enter Discount Amount (Max {raw_subtotal}):", parent=self.root)
        
        if amount is not None:
            if amount < 0:
                messagebox.showerror("Error", "Discount cannot be negative.")
            elif amount >= raw_subtotal:
                messagebox.showerror("Error", "Discount cannot exceed the subtotal.")
            else:
                self.discount_amount = amount
                self.update_cart_display()

    def update_cart_display(self):
        self.cart_text.delete(1.0, tk.END)
        self.subtotal = 0.0
        
        self.cart_text.insert(tk.END, f"{'ITEM':<20} {'QTY':<5} {'TOTAL':<10}\n")
        self.cart_text.insert(tk.END, "-"*40 + "\n")
        
        for item in self.cart:
            line_total = item['price'] * item['qty']
            self.subtotal += line_total
            self.cart_text.insert(tk.END, f"{item['title'][:18]:<20} {item['qty']:<5} {line_total:<10.2f}\n")
        
        # Calculate Final
        self.final_total = self.subtotal - self.discount_amount
        
        self.cart_text.insert(tk.END, "-"*40 + "\n")
        self.cart_text.insert(tk.END, f"Subtotal: {self.subtotal:,.2f}\n")
        if self.discount_amount > 0:
            self.cart_text.insert(tk.END, f"Discount: -{self.discount_amount:,.2f}\n")
        
        self.total_label.config(text=f"Total: KES {self.final_total:,.2f}")
        
        # Recalculate change if user already typed amount
        self.calculate_change()

    def calculate_change(self, event=None):
        try:
            paid_str = self.amount_paid_entry.get()
            if not paid_str:
                self.change_label.config(text="Change: KES 0.00")
                return
                
            paid = float(paid_str)
            change = paid - self.final_total
            self.change_label.config(text=f"Change: KES {change:,.2f}")
        except ValueError:
            pass

    def clear_cart(self):
        self.cart = []
        self.discount_amount = 0.0 # Reset discount
        self.update_cart_display()
        self.amount_paid_entry.delete(0, tk.END)
        self.change_label.config(text="Change: KES 0.00")

    def complete_sale(self):
        if not self.cart:
            messagebox.showwarning("Warning", "Cart is empty")
            return
        
        try:
            paid = float(self.amount_paid_entry.get())
            if paid < self.final_total:
                messagebox.showerror("Error", "Insufficient Funds")
                return
            
            # --- PROFIT CALCULATION ---
            # Total Cost of goods
            total_cost = sum(item['cost'] * item['qty'] for item in self.cart)
            # Profit = Final Money Collected - Total Cost
            profit = self.final_total - total_cost
            
            # 1. Update DB
            sale_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            items_json = json.dumps(self.cart)
            
            self.cursor.execute("""
                INSERT INTO sales (sale_date, total_amount, discount, total_profit, payment_method, items_json) 
                VALUES (?, ?, ?, ?, ?, ?)
            """, (sale_date, self.final_total, self.discount_amount, profit, self.payment_var.get(), items_json))
            
            # 2. Update Stock & Firebase
            for item in self.cart:
                self.cursor.execute("UPDATE products SET stock = stock - ? WHERE sku=?", (item['qty'], item['sku']))
                
                # Firebase Update (Background)
                new_stock_res = self.cursor.execute("SELECT stock FROM products WHERE sku=?", (item['sku'],)).fetchone()
                if new_stock_res:
                    new_stock = new_stock_res[0]
                    threading.Thread(target=lambda s=item['sku'], st=new_stock: requests.patch(f"{FIREBASE_URL}/products/{s}.json", json={"stock": st}), daemon=True).start()

            self.conn.commit()
            
            # 3. Print Receipt
            receipt_data = {
                'date': sale_date,
                'items': self.cart,
                'subtotal': self.subtotal,
                'discount': self.discount_amount,
                'total': self.final_total,
                'paid': paid,
                'change': paid - self.final_total
            }
            self.print_receipt(receipt_data)
            
            # 4. Upload Sale to Firebase
            sale_data = {
                "date": sale_date,
                "amount": self.final_total,
                "discount": self.discount_amount,
                "profit": profit,
                "method": self.payment_var.get(),
                "user": self.current_user
            }
            threading.Thread(target=lambda: requests.post(f"{FIREBASE_URL}/sales.json", json=sale_data), daemon=True).start()

            messagebox.showinfo("Success", f"Sale Complete!\nChange: {paid - self.final_total:,.2f}")
            self.clear_cart()
            self.refresh_inventory()
            
        except ValueError:
            messagebox.showerror("Error", "Invalid Amount Paid")
        except Exception as e:
            messagebox.showerror("Error", f"An error occurred: {e}")

    def print_receipt(self, data):
        """Modified to include Discount on receipt"""
        if not win32print:
            return

        # Format Receipt Text
        txt = "      HERIWADI BOOKSHOP      \n"
        txt += "      Tel: 0700-000-000      \n"
        txt += "-----------------------------\n"
        txt += f"Date: {data['date']}\n"
        txt += f"Served by: {self.current_user}\n"
        txt += "-----------------------------\n"
        txt += "ITEM             QTY    TOTAL\n"
        for item in data['items']:
            # Truncate title if too long
            title = (item['title'][:14] + '..') if len(item['title']) > 14 else item['title']
            txt += f"{title:<16} {item['qty']:<3} {item['price']*item['qty']:>8.2f}\n"
        txt += "-----------------------------\n"
        txt += f"SUBTOTAL:      KES {data['subtotal']:,.2f}\n"
        if data['discount'] > 0:
            txt += f"DISCOUNT:     -KES {data['discount']:,.2f}\n"
        txt += f"TOTAL:         KES {data['total']:,.2f}\n"
        txt += "-----------------------------\n"
        txt += f"PAID:          KES {data['paid']:,.2f}\n"
        txt += f"CHANGE:        KES {data['change']:,.2f}\n"
        txt += "-----------------------------\n"
        txt += "      Thank You! Karibu!      \n\n\n\n"

        copies = ["*** CUSTOMER COPY ***", "*** SHOP COPY ***"]
        
        for copy in copies:
            try:
                final_print = f"{copy}\n{txt}"
                
                hPrinter = win32print.OpenPrinter(PRINTER_NAME)
                try:
                    hJob = win32print.StartDocPrinter(hPrinter, 1, ("Receipt", None, "RAW"))
                    try:
                        win32print.StartPagePrinter(hPrinter)
                        win32print.WritePrinter(hPrinter, final_print.encode("utf-8"))
                        # Cut Paper Command (Standard ESC/POS)
                        win32print.WritePrinter(hPrinter, b'\x1d\x56\x42\x00')
                        win32print.EndPagePrinter(hPrinter)
                    finally:
                        win32print.EndDocPrinter(hPrinter)
                finally:
                    win32print.ClosePrinter(hPrinter)
            except Exception as e:
                print(f"Printing Error: {e}")

    # =========================================================================
    # INVENTORY LOGIC (CRUD)
    # =========================================================================
    def sync_inventory_from_firebase(self):
        try:
            r = requests.get(f"{FIREBASE_URL}/products.json")
            if r.status_code == 200 and r.json():
                data = r.json()
                if isinstance(data, dict):
                    items = data.values()
                else:
                    items = [x for x in data if x is not None]
                
                conn = sqlite3.connect('bookshop.db')
                cur = conn.cursor()
                
                for i in items:
                    if 'sku' not in i: continue
                    cur.execute('''
                        INSERT OR REPLACE INTO products (sku, title, author_supplier, category, product_type, price, cost_price, stock, date_added)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (i.get('sku'), i.get('title'), i.get('author_supplier'), i.get('category'), i.get('product_type'), 
                          float(i.get('price',0)), float(i.get('cost_price',0)), int(i.get('stock',0)), i.get('date_added')))
                
                conn.commit()
                conn.close()
                # Use after() to update UI from main thread
                self.root.after(0, self.refresh_inventory)
        except Exception as e:
            print(f"Sync Error: {e}")

    def refresh_inventory(self):
        self.inventory_tree.delete(*self.inventory_tree.get_children())
        for row in self.cursor.execute("SELECT sku, title, product_type, price, cost_price, stock FROM products"):
            self.inventory_tree.insert('', 'end', values=row)

    def reset_form_for_new(self):
        if self.current_role == "Attendant": return
        for k, v in self.inv_entries.items():
            v.config(state='normal')
            if isinstance(v, ttk.Combobox): v.set('')
            else: v.delete(0, tk.END)
        self.inv_entries['sku'].config(bg="white")

    def on_inventory_select(self, event):
        selected = self.inventory_tree.selection()
        if not selected: return
        values = self.inventory_tree.item(selected[0])['values']
        
        self.reset_form_for_new()
        
        # Populate basic fields
        self.inv_entries['sku'].insert(0, values[0])
        self.inv_entries['title'].insert(0, values[1])
        self.inv_entries['product_type'].set(values[2])
        self.inv_entries['price'].insert(0, values[3])
        self.inv_entries['cost_price'].insert(0, values[4])
        self.inv_entries['stock'].insert(0, values[5])
        
        # Get extra fields
        res = self.cursor.execute("SELECT author_supplier, category FROM products WHERE sku=?", (values[0],)).fetchone()
        if res:
            self.inv_entries['author_supplier'].insert(0, res[0])
            self.inv_entries['category'].insert(0, res[1])
            
        # Lock SKU
        self.inv_entries['sku'].config(state='readonly', bg="#cccccc")

    def add_product(self):
        try:
            data = {k: v.get() for k, v in self.inv_entries.items()}
            if not data['sku'] or not data['title']: return
            
            self.cursor.execute("""
                INSERT INTO products (sku, title, author_supplier, category, product_type, price, cost_price, stock, date_added)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (data['sku'], data['title'], data['author_supplier'], data['category'], data['product_type'], 
                  float(data['price']), float(data['cost_price']), int(data['stock']), datetime.now().strftime('%Y-%m-%d')))
            self.conn.commit()
            
            # Cloud Push
            threading.Thread(target=lambda: requests.put(f"{FIREBASE_URL}/products/{data['sku']}.json", json=data), daemon=True).start()
            
            messagebox.showinfo("Success", "Product Added")
            self.refresh_inventory()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def update_product(self):
        try:
            data = {k: v.get() for k, v in self.inv_entries.items()}
            self.cursor.execute("""
                UPDATE products SET title=?, author_supplier=?, category=?, product_type=?, price=?, cost_price=?, stock=?
                WHERE sku=?
            """, (data['title'], data['author_supplier'], data['category'], data['product_type'], 
                  float(data['price']), float(data['cost_price']), int(data['stock']), data['sku']))
            self.conn.commit()
            
            threading.Thread(target=lambda: requests.put(f"{FIREBASE_URL}/products/{data['sku']}.json", json=data), daemon=True).start()
            
            messagebox.showinfo("Success", "Product Updated")
            self.refresh_inventory()
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def delete_product(self):
        sku = self.inv_entries['sku'].get()
        if not sku: return
        if messagebox.askyesno("Confirm", "Delete this product?"):
            self.cursor.execute("DELETE FROM products WHERE sku=?", (sku,))
            self.conn.commit()
            threading.Thread(target=lambda: requests.delete(f"{FIREBASE_URL}/products/{sku}.json"), daemon=True).start()
            self.refresh_inventory()
            self.reset_form_for_new()

    # =========================================================================
    # REPORTS
    # =========================================================================
    def generate_report(self):
        self.sales_tree.delete(*self.sales_tree.get_children())
        self.reports_text.delete(1.0, tk.END)
        
        # Calculate stats
        today = datetime.now().strftime('%Y-%m-%d')
        
        # We need to sum up columns, handling NULLs with COALESCE or Python fallback
        res_today = self.cursor.execute("SELECT sum(total_amount), sum(discount), sum(total_profit) FROM sales WHERE sale_date LIKE ?", (f'{today}%',)).fetchone()
        res_all = self.cursor.execute("SELECT sum(total_amount), sum(discount), sum(total_profit) FROM sales").fetchone()
        
        today_total = res_today[0] if res_today[0] else 0.0
        today_disc = res_today[1] if res_today[1] else 0.0
        today_profit = res_today[2] if res_today[2] else 0.0
        
        all_total = res_all[0] if res_all[0] else 0.0
        all_disc = res_all[1] if res_all[1] else 0.0
        all_profit = res_all[2] if res_all[2] else 0.0
        
        rpt = f"--- TODAY ({today}) ---\n"
        rpt += f"Revenue:  KES {today_total:,.2f}\n"
        rpt += f"Discount: KES {today_disc:,.2f}\n"
        rpt += f"Profit:   KES {today_profit:,.2f}\n\n"
        rpt += "--- ALL TIME ---\n"
        rpt += f"Revenue:  KES {all_total:,.2f}\n"
        rpt += f"Discount: KES {all_disc:,.2f}\n"
        rpt += f"Profit:   KES {all_profit:,.2f}\n"
        
        self.reports_text.insert(tk.END, rpt)
        
        # Fill List
        rows = self.cursor.execute("SELECT id, total_amount, discount, sale_date FROM sales ORDER BY id DESC LIMIT 50").fetchall()
        for r in rows:
            self.sales_tree.insert('', 'end', values=r)

    def export_sales_to_csv(self):
        try:
            filename = f"sales_{datetime.now().strftime('%Y%m%d')}.csv"
            with open(filename, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([i[0] for i in self.cursor.description])
                writer.writerows(self.cursor.execute("SELECT * FROM sales"))
            messagebox.showinfo("Export", f"Sales exported to {filename}")
        except Exception as e:
            messagebox.showerror("Error", str(e))

    def delete_sale_prompt(self):
        selected = self.sales_tree.selection()
        if not selected: return
        sale_id = self.sales_tree.item(selected[0])['values'][0]
        
        if messagebox.askyesno("Delete Sale", "This will revert stock counts locally.\nContinue?"):
            # 1. Revert Stock
            self.cursor.execute("SELECT items_json FROM sales WHERE id=?", (sale_id,))
            items_json = self.cursor.fetchone()[0]
            items = json.loads(items_json)
            for item in items:
                self.cursor.execute("UPDATE products SET stock = stock + ? WHERE sku=?", (item['qty'], item['sku']))
                # Revert Firebase Stock
                new_stock = self.cursor.execute("SELECT stock FROM products WHERE sku=?", (item['sku'],)).fetchone()[0]
                threading.Thread(target=lambda s=item['sku'], st=new_stock: requests.patch(f"{FIREBASE_URL}/products/{s}.json", json={"stock": st}), daemon=True).start()

            # 2. Delete Record
            self.cursor.execute("DELETE FROM sales WHERE id=?", (sale_id,))
            self.conn.commit()
            
            messagebox.showinfo("Deleted", "Sale deleted and stock reverted.")
            self.generate_report()
            self.refresh_inventory()

if __name__ == "__main__":
    initialize_database()
    root = tk.Tk()
    LoginWindow(root, lambda u, r: BookshopPOS(root, u, r))
    root.mainloop()

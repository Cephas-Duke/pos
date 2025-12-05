import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext, simpledialog
import sqlite3
from datetime import datetime
import json
import os
import hashlib
import csv
import threading # For non-blocking Firebase upload
import requests # For communicating with Firebase REST API

# --- TRY IMPORTING PRINTER LIBRARIES ---
try:
    import win32print
    import win32ui
    # Note: If win32print fails, ensure you run 'pip install pywin32'
except ImportError:
    win32print = None
    print("⚠️ WARNING: 'pywin32' not installed. Printing will not work.")

# ==========================================
# CONFIGURATION
# ==========================================
# Make sure this matches your Windows Printer name EXACTLY
PRINTER_NAME = "BTP-R880NP(U) 1" 
# 👇 REPLACE WITH YOUR ACTUAL FIREBASE DB URL
FIREBASE_URL = "https://heriwadi-bookshop-default-rtdb.firebaseio.com" 
# ==========================================

# ==========================================
# --- DATABASE SETUP FUNCTION ---
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
            total_profit REAL DEFAULT 0.0, 
            payment_method TEXT,
            items_json TEXT 
        )
    ''')

    # --- MIGRATION CHECK ---
    try:
        cursor.execute("SELECT total_profit FROM sales LIMIT 1")
    except sqlite3.OperationalError:
        print("⚠️ Updating database: Adding missing column 'total_profit'...")
        cursor.execute("ALTER TABLE sales ADD COLUMN total_profit REAL DEFAULT 0.0")
        conn.commit()
    
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
        admin_pw = hashlib.sha256("admin123".encode()).hexdigest()
        user_pw = hashlib.sha256("user123".encode()).hexdigest()
        
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", 
                            ("admin", admin_pw, "Director"))
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", 
                            ("user", user_pw, "Attendant"))
        conn.commit()
    
    conn.commit()
    conn.close()

# ==========================================
# LOGIN WINDOW
# ==========================================
class LoginWindow:
    def __init__(self, root, on_login_success):
        self.root = root
        self.on_login_success = on_login_success
        self.root.title("🔐 Login - HERIWADI BOOKSHOP")
        self.root.geometry("1000x600") 
        self.login_frame = tk.Frame(root, bg="#2b2b2b")
        self.login_frame.pack(expand=True, fill='both')
        center_frame = tk.Frame(self.login_frame, bg="#2b2b2b")
        center_frame.place(relx=0.5, rely=0.5, anchor='center')
        tk.Label(center_frame, text="HERIWADI POS", font=('Segoe UI', 24, 'bold'), bg="#2b2b2b", fg="#4CAF50").pack(pady=(0, 40))
        tk.Label(center_frame, text="Username:", font=('Segoe UI', 12), bg="#2b2b2b", fg="#cccccc").pack(anchor='w', fill='x')
        self.user_entry = ttk.Entry(center_frame, font=('Segoe UI', 14), width=30)
        self.user_entry.pack(pady=(5, 20))
        self.user_entry.focus()
        tk.Label(center_frame, text="Password:", font=('Segoe UI', 12), bg="#2b2b2b", fg="#cccccc").pack(anchor='w', fill='x')
        self.pass_entry = ttk.Entry(center_frame, font=('Segoe UI', 14), width=30, show="•")
        self.pass_entry.pack(pady=(5, 30))
        self.pass_entry.bind('<Return>', self.attempt_login)
        btn = tk.Button(center_frame, text="LOGIN", command=self.attempt_login, 
                        bg="#2196F3", fg="white", font=('Segoe UI', 12, 'bold'), 
                        relief='flat', padx=20, pady=12, cursor="hand2")
        btn.pack(fill='x')

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
            self.login_frame.destroy() 
            self.on_login_success(username, role)
        else:
            messagebox.showerror("Login Failed", "Invalid Username or Password")

# ==========================================
# MAIN POS APPLICATION
# ==========================================
class BookshopPOS:
    def __init__(self, root, username, role):
        self.root = root
        self.current_user = username
        self.current_role = role 
        self.root.title(f"📚 HERIWADI BOOKSHOP POS | Logged in as: {username.upper()} ({role})")
        self.root.geometry("1300x750")
        
        self.conn = sqlite3.connect('bookshop.db')
        self.cursor = self.conn.cursor()
        
        self.cart = []
        self.cart_total = 0.0
        
        self.create_ui()
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)
        self.refresh_inventory()

    def on_tab_change(self, event):
        selected_tab = self.notebook.tab(self.notebook.select(), "text")
        if "Reports" in selected_tab:
            self.generate_report()
        elif "Inventory" in selected_tab:
            self.refresh_inventory()

    def create_ui(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill='both', expand=True, padx=10, pady=10)
        self.create_sales_tab()
        self.create_inventory_tab()
        self.create_reports_tab()

    # =========================================================================
    # 🛒 SALES TAB
    # =========================================================================
    def create_sales_tab(self):
        sales_frame = ttk.Frame(self.notebook)
        self.notebook.add(sales_frame, text="🛒 POS Terminal")
        left_frame = ttk.Frame(sales_frame)
        left_frame.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        search_frame = ttk.LabelFrame(left_frame, text="🔍 Product Search", padding=10)
        search_frame.pack(fill='x', pady=(0, 10))
        ttk.Label(search_frame, text="SKU / Title:").pack(side='left', padx=5)
        self.search_entry = ttk.Entry(search_frame, width=30)
        self.search_entry.pack(side='left', padx=5)
        self.search_entry.bind('<Return>', lambda e: self.search_product())
        tk.Button(search_frame, text="SEARCH", command=self.search_product, 
                  bg="#2196F3", fg="white", relief="flat").pack(side='left', padx=5)
        self.search_results_frame = ttk.LabelFrame(left_frame, text="Available Products", padding=10)
        self.search_results_frame.pack(fill='both', expand=True, pady=(0, 10))
        self.search_tree = ttk.Treeview(self.search_results_frame, 
                                        columns=('SKU', 'Title', 'Type', 'Price', 'Stock'),
                                        show='headings', height=10)
        self.search_tree.heading('SKU', text='SKU')
        self.search_tree.heading('Title', text='Title')
        self.search_tree.heading('Type', text='Type')
        self.search_tree.heading('Price', text='Price')
        self.search_tree.heading('Stock', text='Stock')
        self.search_tree.column('SKU', width=80)
        self.search_tree.column('Title', width=200)
        self.search_tree.column('Type', width=80)
        self.search_tree.column('Price', width=80)
        self.search_tree.column('Stock', width=60)
        self.search_tree.pack(fill='both', expand=True)
        self.search_tree.bind('<Double-1>', lambda e: self.add_to_cart())
        tk.Button(left_frame, text="➕ ADD TO CART", command=self.add_to_cart, 
                  bg="#FFC107", fg="black", font=('Segoe UI', 10, 'bold'), relief="flat").pack(pady=5, fill='x')
        right_frame = ttk.Frame(sales_frame)
        right_frame.pack(side='right', fill='both', expand=True, padx=10, pady=10)
        cart_frame = ttk.LabelFrame(right_frame, text="🛒 Shopping Cart", padding=10)
        cart_frame.pack(fill='both', expand=True, pady=(0, 10))
        self.cart_text = scrolledtext.ScrolledText(cart_frame, height=15, width=45, bg="#383838", fg="white", font=('Consolas', 11))
        self.cart_text.pack(fill='both', expand=True)
        total_frame = tk.Frame(right_frame, bg="#222222")
        total_frame.pack(fill='x', pady=10)
        tk.Label(total_frame, text="TOTAL TO PAY:", font=('Segoe UI', 14), bg="#222222", fg="#aaaaaa").pack(anchor='w')
        self.total_label = tk.Label(total_frame, text="KES 0.00", font=('Segoe UI', 24, 'bold'), bg="#222222", fg="#4CAF50")
        self.total_label.pack(anchor='e')
        pay_frame = ttk.LabelFrame(right_frame, text="Payment Details", padding=10)
        pay_frame.pack(fill='x', pady=10)
        ttk.Label(pay_frame, text="Method:").grid(row=0, column=0, pady=5, sticky='w')
        self.payment_var = tk.StringVar(value="Cash")
        ttk.Combobox(pay_frame, textvariable=self.payment_var, values=["Cash", "M-Pesa", "Card"], state="readonly").grid(row=0, column=1, padx=5, sticky='ew')
        ttk.Label(pay_frame, text="Amount Paid:").grid(row=1, column=0, pady=5, sticky='w')
        self.amount_paid_entry = ttk.Entry(pay_frame)
        self.amount_paid_entry.grid(row=1, column=1, padx=5, sticky='ew')
        self.amount_paid_entry.bind('<KeyRelease>', self.calculate_change)
        self.change_label = tk.Label(pay_frame, text="Change: KES 0.00", bg="#2b2b2b", fg="#FFC107", font=('Segoe UI', 11, 'bold'))
        self.change_label.grid(row=2, column=0, columnspan=2, pady=10)
        btn_frame = tk.Frame(right_frame, bg="#2b2b2b")
        btn_frame.pack(fill='x')
        tk.Button(btn_frame, text="✅ COMPLETE SALE", command=self.complete_sale, 
                  bg="#4CAF50", fg="white", font=('Segoe UI', 12, 'bold'), relief="flat", pady=10).pack(side='left', fill='x', expand=True, padx=(0, 5))
        tk.Button(btn_frame, text="❌ CLEAR", command=self.clear_cart, 
                  bg="#F44336", fg="white", font=('Segoe UI', 12, 'bold'), relief="flat", pady=10).pack(side='left', fill='x', expand=True, padx=(5, 0))

    # =========================================================================
    # 📦 INVENTORY TAB
    # =========================================================================
    def create_inventory_tab(self):
        inventory_frame = ttk.Frame(self.notebook)
        self.notebook.add(inventory_frame, text="📦 Inventory")
        form_frame = ttk.LabelFrame(inventory_frame, text="Item Details", padding=10)
        form_frame.pack(fill='x', padx=10, pady=10)
        self.inventory_entries = {}
        fields = [('SKU (Item Code)', 'sku', 'entry', 0), ('Title', 'title', 'entry', 0),
                  ('Author/Supplier', 'author_supplier', 'entry', 1), ('Category', 'category', 'entry', 1),
                  ('Type', 'product_type', 'combo', 2), ('Price (Selling)', 'price', 'entry', 2),
                  ('Cost Price', 'cost_price', 'entry', 3), ('Stock Qty', 'stock', 'entry', 3)]
        for i in range(4): form_frame.columnconfigure(i, weight=1)
        for i, (label, key, widget_type, row_num) in enumerate(fields):
            if key == 'cost_price' and self.current_role == "Attendant": continue 
            col_idx = (i % 2) * 2
            ttk.Label(form_frame, text=label).grid(row=row_num, column=col_idx, sticky='w', padx=5, pady=5)
            if widget_type == 'combo':
                entry = ttk.Combobox(form_frame, values=["Book", "Stationery", "Other"], state='readonly')
            else:
                entry = ttk.Entry(form_frame)
            entry.grid(row=row_num, column=col_idx+1, sticky='ew', padx=5, pady=5)
            self.inventory_entries[key] = entry
        btn_frame = tk.Frame(form_frame, bg="#2b2b2b")
        btn_frame.grid(row=4, column=0, columnspan=4, pady=15)
        self.btn_new = tk.Button(btn_frame, text="✨ RESET FORM", command=self.reset_form_for_new, bg="#9E9E9E", fg="white", relief="flat", padx=15)
        self.btn_add = tk.Button(btn_frame, text="➕ ADD ITEM", command=self.add_product, bg="#4CAF50", fg="white", relief="flat", padx=15)
        self.btn_update = tk.Button(btn_frame, text="💾 UPDATE", command=self.update_product, bg="#2196F3", fg="white", relief="flat", padx=15)
        self.btn_delete = tk.Button(btn_frame, text="🗑️ DELETE", command=self.delete_product, bg="#F44336", fg="white", relief="flat", padx=15)
        self.btn_new.pack(side='left', padx=5)
        self.btn_add.pack(side='left', padx=5)
        self.btn_update.pack(side='left', padx=5)
        self.btn_delete.pack(side='left', padx=5)
        if self.current_role == "Attendant":
            self.btn_new.config(state="disabled", bg="#444444")
            self.btn_add.config(state="disabled", bg="#444444")
            self.btn_update.config(state="disabled", bg="#444444")
            self.btn_delete.config(state="disabled", bg="#444444")
            for key, entry in self.inventory_entries.items(): entry.config(state='disabled')
            tk.Label(form_frame, text="🔒 RESTRICTED ACCESS: View Only", fg="#F44336", bg="#2b2b2b").grid(row=5, column=0, columnspan=4)
        list_frame = ttk.LabelFrame(inventory_frame, text="Stock List", padding=10)
        list_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.inventory_tree = ttk.Treeview(list_frame, columns=('SKU', 'Title', 'Type', 'Category', 'Price', 'Cost', 'Stock'), show='headings')
        headers = ['SKU', 'Title', 'Type', 'Category', 'Price', 'Cost', 'Stock']
        for h in headers:
            self.inventory_tree.heading(h, text=h)
            self.inventory_tree.column(h, width=100)
        self.inventory_tree.column('Title', width=250)
        if self.current_role == "Attendant":
             self.inventory_tree.heading('Cost', text='')
             self.inventory_tree.column('Cost', width=0, stretch=False)
        self.inventory_tree.pack(side='left', fill='both', expand=True)
        scroll = ttk.Scrollbar(list_frame, command=self.inventory_tree.yview)
        scroll.pack(side='right', fill='y')
        self.inventory_tree.configure(yscrollcommand=scroll.set)
        if self.current_role != "Attendant":
            self.inventory_tree.bind('<<TreeviewSelect>>', self.on_inventory_select)
            self.reset_form_for_new()
        
    # =========================================================================
    # 📈 REPORTS TAB
    # =========================================================================
    def create_reports_tab(self):
        reports_frame = ttk.Frame(self.notebook)
        self.notebook.add(reports_frame, text="📈 Reports")
        tool_frame = tk.Frame(reports_frame, bg="#2b2b2b")
        tool_frame.pack(fill='x', padx=10, pady=10)
        tk.Button(tool_frame, text="🔄 REFRESH", command=self.generate_report, bg="#2196F3", fg="white", relief="flat").pack(side='left', padx=5)
        if self.current_role == "Director":
            tk.Button(tool_frame, text="📤 EXPORT CSV", command=self.export_sales_to_csv, bg="#FF9800", fg="white", relief="flat").pack(side='left', padx=5)
            self.btn_del_sale = tk.Button(tool_frame, text="🗑️ DELETE SALE", command=self.delete_sale_prompt, bg="#F44336", fg="white", relief="flat")
            self.btn_del_sale.pack(side='right', padx=5)
        split_frame = tk.Frame(reports_frame, bg="#2b2b2b")
        split_frame.pack(fill='both', expand=True, padx=10, pady=10)
        self.reports_text = scrolledtext.ScrolledText(split_frame, width=50, bg="#383838", fg="white", font=('Consolas', 10))
        self.reports_text.pack(side='left', fill='both', expand=True, padx=(0, 5))
        self.sales_tree = ttk.Treeview(split_frame, columns=('ID', 'Total', 'Date'), show='headings')
        self.sales_tree.heading('ID', text='ID')
        self.sales_tree.heading('Total', text='Total')
        self.sales_tree.heading('Date', text='Date')
        self.sales_tree.column('ID', width=50)
        self.sales_tree.pack(side='right', fill='both', expand=True, padx=(5, 0))
        if self.current_role == "Director":
            self.sales_tree.bind('<Double-1>', lambda e: self.delete_sale_prompt())

    # =========================================================================
    # --- LOGIC & PRINTING & UPLOADING ---
    # =========================================================================

    def print_receipt(self, receipt_data):
        """
        Sends formatted text to the Windows POS Printer
        """
        if not win32print:
            messagebox.showwarning("Printing Error", "Required printer libraries not installed ('pywin32').\nReceipt not printed.")
            return

        try:
            # 1. Format the Receipt Text
            text = "      HERIWADI BOOKSHOP      \n"
            text += "      Tel: 0700-000-000      \n"
            text += "-----------------------------\n"
            text += f"Date: {receipt_data['date']}\n"
            text += f"Served by: {self.current_user}\n"
            text += "-----------------------------\n"
            text += "ITEM           QTY     PRICE\n"
            text += "-----------------------------\n"
            
            for item in receipt_data['items']:
                # Truncate title if too long
                title = (item['title'][:12] + '..') if len(item['title']) > 12 else item['title']
                line = f"{title:<14} {item['qty']:<3} {item['price']*item['qty']:>8.2f}\n"
                text += line
                
            text += "-----------------------------\n"
            text += f"TOTAL:         KES {receipt_data['total']:,.2f}\n"
            text += f"PAID:          KES {receipt_data['paid']:,.2f}\n"
            text += f"CHANGE:        KES {receipt_data['change']:,.2f}\n"
            text += "-----------------------------\n"
            text += "     Thank You! Karibu!      \n"
            text += "\n\n\n\n" # Feed lines
            
            # 2. Send to Printer
            hPrinter = win32print.OpenPrinter(PRINTER_NAME)
            try:
                hJob = win32print.StartDocPrinter(hPrinter, 1, ("Receipt", None, "RAW"))
                try:
                    win32print.StartPagePrinter(hPrinter)
                    win32print.WritePrinter(hPrinter, text.encode("utf-8"))
                    # Cut Paper Command (Standard ESC/POS: GS V 66 0)
                    win32print.WritePrinter(hPrinter, b'\x1d\x56\x42\x00') 
                    win32print.EndPagePrinter(hPrinter)
                finally:
                    win32print.EndDocPrinter(hPrinter)
            finally:
                win32print.ClosePrinter(hPrinter)
                
        except Exception as e:
            messagebox.showerror("Printer Error", f"Could not print receipt.\n\nCheck if printer is ON and name is correct.\n\nDetails: {str(e)}")

    def upload_to_firebase(self, data):
        """Sends data to the web dashboard asynchronously using requests."""
        try:
            url = f"{FIREBASE_URL}/sales.json"
            response = requests.post(url, json=data)
            if response.status_code == 200:
                 print("✅ Data successfully uploaded to Firebase.")
            else:
                 print(f"❌ Firebase Upload Failed. Status: {response.status_code}")
        except Exception as e:
            print(f"❌ Upload Failed (Connection Error): {e}")

    def complete_sale(self):
        if not self.cart: return
        
        profit = sum([(i['price'] - i['cost']) * i['qty'] for i in self.cart])
        
        try:
            paid = float(self.amount_paid_entry.get())
            if paid < self.cart_total:
                messagebox.showerror("Error", "Insufficient Funds")
                return
            
            # 1. Prepare Data & Date String
            date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            items_json = json.dumps(self.cart)

            # 2. Save to LOCAL Database (SQLite) and update stock
            self.cursor.execute("INSERT INTO sales (sale_date, total_amount, total_profit, payment_method, items_json) VALUES (?,?,?,?,?)",
                                (date_str, self.cart_total, profit, self.payment_var.get(), items_json))
            
            for i in self.cart:
                self.cursor.execute("UPDATE products SET stock = stock - ? WHERE sku=?", (i['qty'], i['sku']))
            self.conn.commit()
            
            # 3. Handle Printing
            receipt_data = {
                'date': date_str,
                'items': self.cart,
                'total': self.cart_total,
                'paid': paid,
                'change': paid - self.cart_total
            }
            self.print_receipt(receipt_data)
            
            # 4. ☁️ Upload to Firebase (Web Dashboard) in a separate thread
            sale_data = {
                "sale_date": date_str,
                "timestamp": date_str, # Used by the dashboard for sorting/charting
                "total_amount": self.cart_total,
                "total_profit": profit,
                "payment_method": self.payment_var.get(),
                "items": self.cart,
                "cashier": self.current_user
            }
            threading.Thread(target=self.upload_to_firebase, args=(sale_data,), daemon=True).start()

            # 5. UI Reset & Success
            messagebox.showinfo("Success", f"Sale Complete!\nChange: {paid - self.cart_total:,.2f}")
            self.cart = []
            self.update_cart_ui()
            self.amount_paid_entry.delete(0, 'end')
            self.refresh_inventory()
            
        except ValueError: messagebox.showerror("Error", "Invalid Amount Paid")
        except sqlite3.OperationalError as e:
             messagebox.showerror("Database Error", f"Database operation failed.\nError: {e}")
        except Exception as e:
             # Catch all general errors that weren't specific to SQL or Value errors
             messagebox.showerror("System Error", f"An unexpected error occurred during sale completion.\nError: {e}")

    # --- Other Standard Methods ---
    def reset_form_for_new(self):
        if self.current_role == "Attendant": return
        for key, entry in self.inventory_entries.items():
            entry.config(state='normal')
            entry.delete(0, 'end')
            if key == 'product_type': entry.set('Book')
        self.inventory_entries['sku'].config(state='normal', background="#ffffff")
        self.inventory_entries['sku'].focus()

    def on_inventory_select(self, event):
        selection = self.inventory_tree.selection()
        if not selection: return
        vals = self.inventory_tree.item(selection[0])['values']
        if self.current_role == "Attendant": return
        for entry in self.inventory_entries.values():
            entry.config(state='normal')
            entry.delete(0, 'end')
        self.inventory_entries['sku'].insert(0, vals[0])
        self.inventory_entries['title'].insert(0, vals[1])
        self.inventory_entries['product_type'].set(vals[2])
        self.inventory_entries['category'].insert(0, vals[3])
        self.inventory_entries['price'].insert(0, vals[4])
        self.inventory_entries['cost_price'].insert(0, vals[5])
        self.inventory_entries['stock'].insert(0, vals[6])
        self.cursor.execute("SELECT author_supplier FROM products WHERE sku=?", (vals[0],))
        res = self.cursor.fetchone()
        if res: self.inventory_entries['author_supplier'].insert(0, res[0])
        self.inventory_entries['sku'].config(state='readonly', background="#cccccc")

    def add_product(self):
        try:
            data = {k: v.get().strip() for k, v in self.inventory_entries.items() if k in self.inventory_entries} 
            if not data['sku'] or not data['title']: return
            cost_price = float(data.get('cost_price') or 0.0) 
            self.cursor.execute('INSERT INTO products (sku, title, author_supplier, category, product_type, price, cost_price, stock, date_added) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                                (data['sku'], data['title'], data['author_supplier'], data['category'], data['product_type'], float(data['price']), cost_price, int(data['stock']), datetime.now().strftime('%Y-%m-%d')))
            self.conn.commit()
            messagebox.showinfo("Success", "Product Added!")
            self.refresh_inventory()
            self.reset_form_for_new()
        except Exception as e: messagebox.showerror("Error", str(e))

    def update_product(self):
        sku = self.inventory_entries['sku'].get()
        if self.inventory_entries['sku']['state'] == 'normal': return
        try:
            data = {k: v.get().strip() for k, v in self.inventory_entries.items() if k in self.inventory_entries}
            cost_price_val = float(data.get('cost_price') or 0.0)
            self.cursor.execute('UPDATE products SET title=?, author_supplier=?, category=?, product_type=?, price=?, cost_price=?, stock=? WHERE sku=?',
                                (data['title'], data['author_supplier'], data['category'], data['product_type'], float(data['price']), cost_price_val, int(data['stock']), sku))
            self.conn.commit()
            messagebox.showinfo("Success", "Product Updated!")
            self.refresh_inventory()
            self.reset_form_for_new()
        except Exception as e: messagebox.showerror("Error", str(e))

    def delete_product(self):
        sku = self.inventory_entries['sku'].get()
        if not sku: return
        if messagebox.askyesno("Confirm", f"Delete item {sku}?"):
            self.cursor.execute("DELETE FROM products WHERE sku=?", (sku,))
            self.conn.commit()
            self.refresh_inventory()
            self.reset_form_for_new()

    def refresh_inventory(self):
        for i in self.inventory_tree.get_children(): self.inventory_tree.delete(i)
        self.cursor.execute('SELECT sku, title, product_type, category, price, cost_price, stock FROM products')
        for row in self.cursor.fetchall(): self.inventory_tree.insert('', 'end', values=row)

    def search_product(self):
        q = self.search_entry.get().strip()
        for i in self.search_tree.get_children(): self.search_tree.delete(i)
        self.cursor.execute("SELECT sku, title, product_type, price, stock, cost_price FROM products WHERE sku LIKE ? OR title LIKE ?", (f'%{q}%', f'%{q}%'))
        for row in self.cursor.fetchall(): self.search_tree.insert('', 'end', values=row[:5], tags=(row[5],))

    def add_to_cart(self):
        sel = self.search_tree.selection()
        if not sel: return
        val = self.search_tree.item(sel[0])['values']
        cost = self.search_tree.item(sel[0])['tags'][0]
        qty = simpledialog.askinteger("Qty", "Enter Quantity:", parent=self.root, minvalue=1, maxvalue=val[4])
        if qty:
            self.cart.append({'sku': val[0], 'title': val[1], 'type': val[2], 'price': float(val[3]), 'cost': float(cost), 'qty': qty})
            self.update_cart_ui()

    def update_cart_ui(self):
        self.cart_text.delete('1.0', 'end')
        self.cart_total = 0.0
        for item in self.cart:
            sub = item['price'] * item['qty']
            self.cart_total += sub
            self.cart_text.insert('end', f"{item['title']} x{item['qty']} = {sub:.2f}\n")
        self.total_label.config(text=f"KES {self.cart_total:,.2f}")

    def calculate_change(self, e):
        try:
            paid = float(self.amount_paid_entry.get())
            self.change_label.config(text=f"Change: KES {paid - self.cart_total:,.2f}")
        except: pass

    def generate_report(self):
        self.reports_text.delete('1.0', 'end')
        show_profit = True if self.current_role == "Director" else False 
        today = datetime.now().strftime('%Y-%m-%d')
        try:
            self.cursor.execute("SELECT count(*), sum(total_amount), sum(total_profit) FROM sales WHERE date(sale_date)=?", (today,))
            res = self.cursor.fetchone()
        except sqlite3.OperationalError:
            self.cursor.execute("SELECT count(*), sum(total_amount) FROM sales WHERE date(sale_date)=?", (today,))
            temp_res = self.cursor.fetchone()
            res = (temp_res[0], temp_res[1], 0.0)
        txt = f"REPORT ({today})\nTransactions: {res[0] or 0}\nRevenue: KES {res[1] or 0:,.2f}\n"
        if show_profit: txt += f"Profit: KES {res[2] or 0:,.2f}\n"
        else: txt += "Profit: [HIDDEN]\n" 
        self.reports_text.insert('end', txt)
        for i in self.sales_tree.get_children(): self.sales_tree.delete(i)
        self.cursor.execute("SELECT id, total_amount, sale_date FROM sales ORDER BY id DESC LIMIT 20")
        for row in self.cursor.fetchall(): self.sales_tree.insert('', 'end', values=row)

    def export_sales_to_csv(self):
        filename = f"sales_export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        self.cursor.execute('SELECT * FROM sales')
        sales_data = self.cursor.fetchall()
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                writer = csv.writer(csvfile)
                writer.writerow(['ID', 'Date', 'Total', 'Profit', 'Method', 'Items'])
                writer.writerows(sales_data)
            messagebox.showinfo("Export Successful", f"Saved to {filename}")
        except Exception as e: messagebox.showerror("Error", str(e))
        
    def delete_sale_prompt(self):
        selection = self.sales_tree.selection()
        if not selection: return
        sale_id = self.sales_tree.item(selection[0])['values'][0]
        if messagebox.askyesno("Confirm", f"Delete Sale {sale_id}?"):
            try:
                self.cursor.execute('SELECT items_json FROM sales WHERE id = ?', (sale_id,))
                items = json.loads(self.cursor.fetchone()[0])
                for item in items:
                    self.cursor.execute('UPDATE products SET stock = stock + ? WHERE sku = ?', (item['qty'], item['sku']))
                self.cursor.execute('DELETE FROM sales WHERE id = ?', (sale_id,))
                self.conn.commit()
                self.generate_report()
            except Exception as e: messagebox.showerror("Error", str(e))

    def clear_cart(self):
        self.cart = []
        self.update_cart_ui()
        self.amount_paid_entry.delete(0, 'end')
        self.change_label.config(text="Change: KES 0.00")
        messagebox.showinfo("Cart Cleared", "The shopping cart has been emptied.")

    def __del__(self):
        if hasattr(self, 'conn'): self.conn.close()

if __name__ == "__main__":
    initialize_database()
    def start_app(user, role): app = BookshopPOS(root, user, role)
    root = tk.Tk()
    style = ttk.Style()
    try:
        root.tk.call("source", "azure.tcl")
        root.tk.call("set_theme", "dark")
    except:
        style.theme_use('clam')
        root.configure(bg="#2b2b2b")
    login = LoginWindow(root, start_app)
    root.mainloop()

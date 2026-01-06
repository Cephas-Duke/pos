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
# THEME CONFIGURATION
# ==========================================
COLORS = {
    "bg_dark": "#1e1e1e",       # Main Window Background
    "bg_panel": "#2d2d2d",      # Panels/Frames
    "text_light": "#ffffff",    # Main Text
    "text_dim": "#a0a0a0",      # Secondary Text
    "accent_blue": "#3b8ed0",   # Primary Actions
    "accent_green": "#00e676",  # Success/Pay
    "accent_red": "#ef5350",    # Danger/Delete
    "accent_orange": "#ffab40"  # Warning/Discount
}

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

    # --- MIGRATION CHECKS ---
    # Check for total_profit
    try:
        cursor.execute("SELECT total_profit FROM sales LIMIT 1")
    except sqlite3.OperationalError:
        print("⚠️ Updating database: Adding 'total_profit'...")
        cursor.execute("ALTER TABLE sales ADD COLUMN total_profit REAL DEFAULT 0.0")
    
    # Check for discount
    try:
        cursor.execute("SELECT discount FROM sales LIMIT 1")
    except sqlite3.OperationalError:
        print("⚠️ Updating database: Adding 'discount'...")
        cursor.execute("ALTER TABLE sales ADD COLUMN discount REAL DEFAULT 0.0")
    
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
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("admin", admin_pw, "Director"))
        cursor.execute("INSERT INTO users (username, password_hash, role) VALUES (?, ?, ?)", ("user", user_pw, "Attendant"))
        
    conn.commit()
    conn.close()

# ==========================================
# STYLING CLASS
# ==========================================
def apply_styles(root):
    style = ttk.Style(root)
    style.theme_use('clam')
    
    # General Frame Styles
    style.configure("TFrame", background=COLORS["bg_dark"])
    style.configure("Panel.TFrame", background=COLORS["bg_panel"])
    style.configure("TLabel", background=COLORS["bg_panel"], foreground=COLORS["text_light"], font=('Segoe UI', 11))
    style.configure("Title.TLabel", background=COLORS["bg_panel"], foreground=COLORS["accent_blue"], font=('Segoe UI', 14, 'bold'))
    
    # Buttons
    style.configure("TButton", font=('Segoe UI', 10, 'bold'), borderwidth=0, focuscolor="none")
    style.map("TButton", background=[('active', '#444444')])

    # Treeview (Lists)
    style.configure("Treeview", 
                    background="#333333", 
                    foreground="white", 
                    fieldbackground="#333333", 
                    font=('Segoe UI', 11),
                    rowheight=30)
    style.configure("Treeview.Heading", font=('Segoe UI', 11, 'bold'), background="#444444", foreground="white")
    style.map("Treeview", background=[('selected', COLORS['accent_blue'])])
    
    # Notebook (Tabs)
    style.configure("TNotebook", background=COLORS["bg_dark"], borderwidth=0)
    style.configure("TNotebook.Tab", background="#444444", foreground="white", padding=[15, 8], font=('Segoe UI', 11))
    style.map("TNotebook.Tab", background=[('selected', COLORS['accent_blue'])])

# ==========================================
# LOGIN WINDOW
# ==========================================
class LoginWindow:
    def __init__(self, root, on_login_success):
        self.root = root
        self.on_login_success = on_login_success
        self.root.title("Login - HERIWADI BOOKSHOP")
        self.root.geometry("900x600")
        self.root.configure(bg=COLORS["bg_dark"])
        
        # Center Box
        center_frame = tk.Frame(root, bg=COLORS["bg_panel"], padx=40, pady=40)
        center_frame.place(relx=0.5, rely=0.5, anchor='center')
        
        # Logo/Title
        tk.Label(center_frame, text="HERIWADI", font=('Segoe UI', 32, 'bold'), bg=COLORS["bg_panel"], fg=COLORS["text_light"]).pack()
        tk.Label(center_frame, text="Management System", font=('Segoe UI', 14), bg=COLORS["bg_panel"], fg=COLORS["accent_blue"]).pack(pady=(0, 30))

        # Inputs
        tk.Label(center_frame, text="Username", font=('Segoe UI', 10, 'bold'), bg=COLORS["bg_panel"], fg=COLORS["text_dim"]).pack(anchor='w')
        self.user_entry = tk.Entry(center_frame, font=('Segoe UI', 14), width=25, bg="#444444", fg="white", insertbackground="white", relief="flat")
        self.user_entry.pack(pady=(5, 15), ipady=5)
        self.user_entry.focus()
        
        tk.Label(center_frame, text="Password", font=('Segoe UI', 10, 'bold'), bg=COLORS["bg_panel"], fg=COLORS["text_dim"]).pack(anchor='w')
        self.pass_entry = tk.Entry(center_frame, font=('Segoe UI', 14), width=25, bg="#444444", fg="white", insertbackground="white", relief="flat", show="•")
        self.pass_entry.pack(pady=(5, 25), ipady=5)
        self.pass_entry.bind('<Return>', self.attempt_login)
        
        # Login Button
        btn = tk.Button(center_frame, text="LOG IN", command=self.attempt_login, 
                        bg=COLORS["accent_blue"], fg="white", font=('Segoe UI', 12, 'bold'), 
                        relief='flat', activebackground="#2c6e91", activeforeground="white", cursor="hand2")
        btn.pack(fill='x', ipady=8)

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
            for widget in self.root.winfo_children(): widget.destroy() # Clear login screen
            self.on_login_success(username, role)
        else:
            messagebox.showerror("Access Denied", "Invalid Username or Password")

# ==========================================
# MAIN POS APPLICATION
# ==========================================
class BookshopPOS:
    def __init__(self, root, username, role):
        self.root = root
        self.current_user = username
        self.current_role = role 
        
        self.root.title(f"HERIWADI BOOKSHOP POS | {username.upper()} ({role})")
        self.root.geometry("1400x850")
        self.root.configure(bg=COLORS["bg_dark"])
        apply_styles(self.root)
        
        self.conn = sqlite3.connect('bookshop.db')
        self.cursor = self.conn.cursor()
        
        # Cart Variables
        self.cart = []
        self.subtotal = 0.0
        self.discount_amount = 0.0
        self.final_total = 0.0
        
        self.create_ui()
        self.notebook.bind("<<NotebookTabChanged>>", self.on_tab_change)
        
        # Initial Load & Sync
        self.refresh_inventory()
        threading.Thread(target=self.sync_inventory_from_firebase, daemon=True).start()

    def on_tab_change(self, event):
        selected_tab = self.notebook.tab(self.notebook.select(), "text")
        if "Reports" in selected_tab:
            self.generate_report()
        elif "Inventory" in selected_tab:
            self.refresh_inventory()

    def create_ui(self):
        # Main Container
        main_container = tk.Frame(self.root, bg=COLORS["bg_dark"])
        main_container.pack(fill='both', expand=True, padx=20, pady=20)

        # Header
        header = tk.Frame(main_container, bg=COLORS["bg_dark"])
        header.pack(fill='x', pady=(0, 15))
        tk.Label(header, text="HERIWADI BOOKSHOP", font=('Segoe UI', 24, 'bold'), bg=COLORS["bg_dark"], fg=COLORS["text_light"]).pack(side='left')
        
        status_color = COLORS['accent_green'] if self.current_role == "Director" else COLORS['accent_blue']
        tk.Label(header, text=f"👤 {self.current_user.upper()}", font=('Segoe UI', 12, 'bold'), bg=status_color, fg="black", padx=10, pady=5).pack(side='right')

        # Tabs
        self.notebook = ttk.Notebook(main_container)
        self.notebook.pack(fill='both', expand=True)
        
        self.create_sales_tab()
        self.create_inventory_tab()
        self.create_reports_tab()

    # =========================================================================
    # 🛒 SALES TAB
    # =========================================================================
    def create_sales_tab(self):
        sales_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(sales_frame, text="🛒 POS Terminal")
        
        # --- LEFT: SEARCH & PRODUCT LIST ---
        left_frame = tk.Frame(sales_frame, bg=COLORS["bg_panel"])
        left_frame.pack(side='left', fill='both', expand=True, padx=10, pady=10)
        
        # Search Bar
        search_box = tk.Frame(left_frame, bg=COLORS["bg_panel"])
        search_box.pack(fill='x', pady=(0, 10))
        tk.Label(search_box, text="Search Product (SKU/Title):", font=('Segoe UI', 11, 'bold')).pack(anchor='w', pady=(0,5))
        
        self.search_entry = tk.Entry(search_box, font=('Segoe UI', 14), bg="#444444", fg="white", relief="flat", insertbackground="white")
        self.search_entry.pack(fill='x', ipady=8)
        self.search_entry.bind('<Return>', lambda e: self.search_product())
        self.search_entry.bind('<KeyRelease>', lambda e: self.search_product()) # Auto search on type

        # Results Table
        self.search_tree = ttk.Treeview(left_frame, columns=('SKU', 'Title', 'Price', 'Stock'), show='headings', height=15)
        self.search_tree.heading('SKU', text='SKU')
        self.search_tree.heading('Title', text='ITEM TITLE')
        self.search_tree.heading('Price', text='PRICE')
        self.search_tree.heading('Stock', text='STOCK')
        
        self.search_tree.column('SKU', width=80)
        self.search_tree.column('Title', width=300)
        self.search_tree.column('Price', width=80)
        self.search_tree.column('Stock', width=60)
        
        self.search_tree.pack(fill='both', expand=True)
        self.search_tree.bind('<Double-1>', lambda e: self.add_to_cart())
        self.search_tree.bind('<Return>', lambda e: self.add_to_cart())

        tk.Button(left_frame, text="ADD SELECTED TO CART ➡", command=self.add_to_cart, 
                  bg=COLORS["accent_blue"], fg="white", font=('Segoe UI', 11, 'bold'), relief="flat", pady=10).pack(fill='x', pady=10)

        # --- RIGHT: CART & PAYMENT ---
        right_frame = tk.Frame(sales_frame, bg="#252525", width=400)
        right_frame.pack(side='right', fill='y', padx=(10, 0), pady=10)
        right_frame.pack_propagate(False) # Force width
        
        tk.Label(right_frame, text="CURRENT ORDER", font=('Segoe UI', 14, 'bold'), bg="#252525", fg="#aaaaaa").pack(pady=10)

        # Cart Display
        self.cart_text = scrolledtext.ScrolledText(right_frame, height=12, bg="#1e1e1e", fg="white", font=('Consolas', 11), relief="flat", padx=10, pady=10)
        self.cart_text.pack(fill='x', padx=10)
        
        # Totals Section
        totals_frame = tk.Frame(right_frame, bg="#252525")
        totals_frame.pack(fill='x', padx=10, pady=10)
        
        self.lbl_subtotal = tk.Label(totals_frame, text="Subtotal: 0.00", font=('Segoe UI', 11), bg="#252525", fg="#cccccc")
        self.lbl_subtotal.pack(anchor='e')
        
        self.lbl_discount = tk.Label(totals_frame, text="Discount: -0.00", font=('Segoe UI', 11), bg="#252525", fg=COLORS["accent_orange"])
        self.lbl_discount.pack(anchor='e')

        tk.Frame(totals_frame, height=2, bg="#444444").pack(fill='x', pady=5) # Divider

        tk.Label(totals_frame, text="TOTAL TO PAY", font=('Segoe UI', 10), bg="#252525", fg="#aaaaaa").pack(anchor='w')
        self.total_label = tk.Label(totals_frame, text="KES 0.00", font=('Segoe UI', 28, 'bold'), bg="#252525", fg=COLORS["accent_green"])
        self.total_label.pack(anchor='e')

        # Action Buttons (Discount & Clear)
        action_row = tk.Frame(right_frame, bg="#252525")
        action_row.pack(fill='x', padx=10)
        
        tk.Button(action_row, text="✂️ DISCOUNT", command=self.prompt_discount, 
                  bg=COLORS["accent_orange"], fg="black", font=('Segoe UI', 10, 'bold'), relief="flat").pack(side='left', fill='x', expand=True, padx=(0,2))
        
        tk.Button(action_row, text="🗑️ CLEAR", command=self.clear_cart, 
                  bg=COLORS["accent_red"], fg="white", font=('Segoe UI', 10, 'bold'), relief="flat").pack(side='left', fill='x', expand=True, padx=(2,0))

        # Payment Inputs
        pay_frame = tk.LabelFrame(right_frame, text="Process Payment", bg="#252525", fg="#aaaaaa", font=('Segoe UI', 10), padx=10, pady=10, relief="flat")
        pay_frame.pack(fill='x', padx=10, pady=10)
        
        self.payment_var = tk.StringVar(value="Cash")
        ttk.Combobox(pay_frame, textvariable=self.payment_var, values=["Cash", "M-Pesa", "Card"], state="readonly", font=('Segoe UI', 12)).pack(fill='x', pady=(0, 10))
        
        self.amount_paid_entry = tk.Entry(pay_frame, font=('Segoe UI', 14), bg="#444444", fg="white", insertbackground="white", relief="flat")
        self.amount_paid_entry.pack(fill='x', ipady=5)
        self.amount_paid_entry.bind('<KeyRelease>', self.calculate_change)
        
        self.change_label = tk.Label(pay_frame, text="Change: KES 0.00", bg="#252525", fg="#aaaaaa", font=('Segoe UI', 11))
        self.change_label.pack(pady=(10, 0))

        # Complete Button
        tk.Button(right_frame, text="✅ COMPLETE SALE", command=self.complete_sale, 
                  bg=COLORS["accent_green"], fg="#1e1e1e", font=('Segoe UI', 14, 'bold'), relief="flat", pady=15, cursor="hand2").pack(fill='x', side='bottom')

    # =========================================================================
    # 📦 INVENTORY TAB
    # =========================================================================
    def create_inventory_tab(self):
        inv_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(inv_frame, text="📦 Inventory")
        
        # Split: Form (Left) vs List (Right)
        main_inv = tk.Frame(inv_frame, bg=COLORS["bg_panel"])
        main_inv.pack(fill='both', expand=True, padx=10, pady=10)
        
        # --- LEFT: INPUT FORM ---
        form_container = tk.LabelFrame(main_inv, text="Item Details", bg=COLORS["bg_panel"], fg="white", padx=15, pady=15, relief="flat")
        form_container.pack(side='left', fill='y', padx=(0, 10))
        
        self.inv_entries = {}
        fields = [('SKU', 'sku'), ('Title', 'title'), ('Author/Sup.', 'author_supplier'), 
                  ('Category', 'category'), ('Type', 'product_type'), 
                  ('Sell Price', 'price'), ('Cost Price', 'cost_price'), ('Stock', 'stock')]
        
        for idx, (lbl, key) in enumerate(fields):
            if key == 'cost_price' and self.current_role == "Attendant": continue
            
            tk.Label(form_container, text=lbl, bg=COLORS["bg_panel"], fg="#cccccc").pack(anchor='w', pady=(5,0))
            if key == 'product_type':
                entry = ttk.Combobox(form_container, values=["Book", "Stationery", "Other"], state='readonly')
            else:
                entry = tk.Entry(form_container, bg="#444444", fg="white", relief="flat", insertbackground="white")
            
            entry.pack(fill='x', pady=(0, 5), ipady=4)
            self.inv_entries[key] = entry
            
        # Buttons
        btn_grid = tk.Frame(form_container, bg=COLORS["bg_panel"])
        btn_grid.pack(fill='x', pady=15)
        
        tk.Button(btn_grid, text="New", command=self.reset_form_for_new, bg="#666666", fg="white", width=8, relief="flat").grid(row=0, column=0, padx=2)
        tk.Button(btn_grid, text="Save", command=self.add_product, bg=COLORS["accent_green"], fg="black", width=8, relief="flat").grid(row=0, column=1, padx=2)
        tk.Button(btn_grid, text="Update", command=self.update_product, bg=COLORS["accent_blue"], fg="white", width=8, relief="flat").grid(row=1, column=0, padx=2, pady=5)
        tk.Button(btn_grid, text="Delete", command=self.delete_product, bg=COLORS["accent_red"], fg="white", width=8, relief="flat").grid(row=1, column=1, padx=2, pady=5)

        tk.Button(form_container, text="☁ Sync Cloud", command=lambda: threading.Thread(target=self.sync_inventory_from_firebase, daemon=True).start(), 
                  bg=COLORS["accent_orange"], fg="black", relief="flat").pack(fill='x', pady=5)

        # --- RIGHT: LIST ---
        list_container = tk.Frame(main_inv, bg=COLORS["bg_panel"])
        list_container.pack(side='right', fill='both', expand=True)
        
        self.inventory_tree = ttk.Treeview(list_container, columns=('SKU', 'Title', 'Type', 'Price', 'Cost', 'Stock'), show='headings')
        headers = ['SKU', 'Title', 'Type', 'Price', 'Cost', 'Stock']
        for h in headers:
            self.inventory_tree.heading(h, text=h)
            self.inventory_tree.column(h, width=80)
        self.inventory_tree.column('Title', width=200)
        
        if self.current_role == "Attendant":
            self.inventory_tree.column('Cost', width=0, stretch=False) # Hide cost
            
        self.inventory_tree.pack(side='left', fill='both', expand=True)
        
        scroll = ttk.Scrollbar(list_container, command=self.inventory_tree.yview)
        scroll.pack(side='right', fill='y')
        self.inventory_tree.configure(yscrollcommand=scroll.set)
        
        if self.current_role != "Attendant":
            self.inventory_tree.bind('<<TreeviewSelect>>', self.on_inventory_select)

    # =========================================================================
    # 📈 REPORTS TAB
    # =========================================================================
    def create_reports_tab(self):
        rep_frame = ttk.Frame(self.notebook, style="Panel.TFrame")
        self.notebook.add(rep_frame, text="📈 Reports")
        
        toolbar = tk.Frame(rep_frame, bg=COLORS["bg_panel"])
        toolbar.pack(fill='x', padx=10, pady=10)
        
        tk.Button(toolbar, text="🔄 REFRESH STATS", command=self.generate_report, bg=COLORS["accent_blue"], fg="white", relief="flat", padx=15).pack(side='left')
        
        if self.current_role == "Director":
            tk.Button(toolbar, text="🗑️ VOID SELECTED SALE", command=self.delete_sale_prompt, bg=COLORS["accent_red"], fg="white", relief="flat", padx=15).pack(side='right')
            tk.Button(toolbar, text="📤 EXPORT CSV", command=self.export_sales_to_csv, bg="#FF9800", fg="black", relief="flat", padx=15).pack(side='right', padx=10)

        content = tk.Frame(rep_frame, bg=COLORS["bg_panel"])
        content.pack(fill='both', expand=True, padx=10, pady=(0, 10))
        
        # Report Text
        self.reports_text = scrolledtext.ScrolledText(content, width=40, bg="#1e1e1e", fg="white", font=('Consolas', 11), relief="flat", padx=10, pady=10)
        self.reports_text.pack(side='left', fill='y')
        
        # Sales List
        self.sales_tree = ttk.Treeview(content, columns=('ID', 'Total', 'Disc.', 'Date'), show='headings')
        self.sales_tree.heading('ID', text='ID')
        self.sales_tree.heading('Total', text='Total Paid')
        self.sales_tree.heading('Disc.', text='Discount')
        self.sales_tree.heading('Date', text='Time')
        
        self.sales_tree.column('ID', width=50)
        self.sales_tree.column('Disc.', width=80)
        self.sales_tree.pack(side='right', fill='both', expand=True, padx=(10,0))

    # =========================================================================
    # LOGIC: DISCOUNT, SALES & PRINTING
    # =========================================================================

    def prompt_discount(self):
        """Logic for the Discount Button"""
        if not self.cart:
            messagebox.showwarning("Cart Empty", "Add items before applying a discount.")
            return

        amount = simpledialog.askfloat("Apply Discount", "Enter Discount Amount (KES):", parent=self.root, minvalue=0.0)
        
        if amount is not None:
            if amount >= self.subtotal:
                messagebox.showerror("Error", "Discount cannot exceed Subtotal!")
                return
            
            self.discount_amount = amount
            self.update_cart_ui()

    def update_cart_ui(self):
        self.cart_text.delete(1.0, 'end')
        self.subtotal = 0.0
        
        # 1. Calculate Subtotal
        for item in self.cart:
            line_total = item['price'] * item['qty']
            self.subtotal += line_total
            self.cart_text.insert('end', f"{item['title'][:20]:<20} x{item['qty']}  {line_total:>8.2f}\n")
        
        # 2. Calculate Final
        self.final_total = self.subtotal - self.discount_amount
        
        # 3. Update Labels
        self.lbl_subtotal.config(text=f"Subtotal: {self.subtotal:,.2f}")
        self.lbl_discount.config(text=f"Discount: -{self.discount_amount:,.2f}")
        self.total_label.config(text=f"KES {self.final_total:,.2f}")
        
        self.calculate_change()

    def calculate_change(self, event=None):
        try:
            paid_str = self.amount_paid_entry.get()
            if not paid_str: 
                self.change_label.config(text="Change: KES 0.00")
                return
                
            paid = float(paid_str)
            change = paid - self.final_total
            
            color = COLORS["accent_green"] if change >= 0 else COLORS["accent_red"]
            self.change_label.config(text=f"Change: KES {change:,.2f}", fg=color)
        except ValueError:
            pass

    def complete_sale(self):
        if not self.cart: return
        
        try:
            paid = float(self.amount_paid_entry.get())
            if paid < self.final_total:
                messagebox.showerror("Error", "Insufficient Funds")
                return
            
            # --- PROFIT CALCULATION ---
            # Cost of Goods Sold
            cogs = sum([i['cost'] * i['qty'] for i in self.cart])
            # Revenue = Final Total (after discount)
            # Profit = Revenue - COGS
            profit = self.final_total - cogs
            
            date_str = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            items_json = json.dumps(self.cart)

            # 1. DB Insert
            self.cursor.execute("""
                INSERT INTO sales (sale_date, total_amount, discount, total_profit, payment_method, items_json) 
                VALUES (?,?,?,?,?,?)
            """, (date_str, self.final_total, self.discount_amount, profit, self.payment_var.get(), items_json))
            
            # 2. Stock Update
            for i in self.cart:
                self.cursor.execute("UPDATE products SET stock = stock - ? WHERE sku=?", (i['qty'], i['sku']))
                new_stock = self.cursor.execute("SELECT stock FROM products WHERE sku=?", (i['sku'],)).fetchone()[0]
                # Background Cloud Sync
                threading.Thread(target=lambda s=i['sku'], st=new_stock: requests.patch(f"{FIREBASE_URL}/products/{s}.json", json={"stock": st}), daemon=True).start()

            self.conn.commit()
            
            # 3. Receipt
            receipt_data = {
                'date': date_str,
                'items': self.cart,
                'subtotal': self.subtotal,
                'discount': self.discount_amount,
                'total': self.final_total,
                'paid': paid,
                'change': paid - self.final_total
            }
            self.print_receipt(receipt_data)
            
            # 4. Upload Sale
            sale_data = {
                "date": date_str, "amount": self.final_total, "profit": profit, 
                "discount": self.discount_amount, "method": self.payment_var.get(), "user": self.current_user
            }
            threading.Thread(target=lambda: requests.post(f"{FIREBASE_URL}/sales.json", json=sale_data), daemon=True).start()

            messagebox.showinfo("Success", f"Sale Complete!\nChange: {paid - self.final_total:,.2f}")
            self.clear_cart()
            self.refresh_inventory()
            
        except ValueError: messagebox.showerror("Error", "Invalid Amount Paid")
        except Exception as e: messagebox.showerror("Error", str(e))

    def clear_cart(self):
        self.cart = []
        self.discount_amount = 0.0
        self.update_cart_ui()
        self.amount_paid_entry.delete(0, 'end')

    def print_receipt(self, data):
        """Updated Receipt Format with Discount"""
        if not win32print: return

        txt = "      HERIWADI BOOKSHOP      \n"
        txt += "      Tel: 0700-000-000      \n"
        txt += "-----------------------------\n"
        txt += f"Date: {data['date']}\n"
        txt += f"Served by: {self.current_user}\n"
        txt += "-----------------------------\n"
        txt += "ITEM             QTY    TOTAL\n"
        for item in data['items']:
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
                final = f"{copy}\n{txt}"
                hPrinter = win32print.OpenPrinter(PRINTER_NAME)
                try:
                    hJob = win32print.StartDocPrinter(hPrinter, 1, ("Receipt", None, "RAW"))
                    try:
                        win32print.StartPagePrinter(hPrinter)
                        win32print.WritePrinter(hPrinter, final.encode("utf-8"))
                        win32print.WritePrinter(hPrinter, b'\x1d\x56\x42\x00') # Cut
                        win32print.EndPagePrinter(hPrinter)
                    finally: win32print.EndDocPrinter(hPrinter)
                finally: win32print.ClosePrinter(hPrinter)
            except: pass

    # =========================================================================
    # INVENTORY LOGIC & CLOUD SYNC
    # =========================================================================
    def search_product(self):
        query = self.search_entry.get().strip()
        self.search_tree.delete(*self.search_tree.get_children())
        
        sql = "SELECT sku, title, price, stock FROM products WHERE stock > 0"
        params = ()
        if query:
            sql += " AND (sku LIKE ? OR title LIKE ?)"
            params = (f'%{query}%', f'%{query}%')
            
        self.cursor.execute(sql + " LIMIT 30", params)
        for row in self.cursor.fetchall():
            self.search_tree.insert('', 'end', values=row)

    def add_to_cart(self):
        sel = self.search_tree.selection()
        if not sel: return
        vals = self.search_tree.item(sel[0])['values']
        sku, title, price, stock = vals[0], vals[1], float(vals[2]), int(vals[3])

        for item in self.cart:
            if item['sku'] == sku:
                if item['qty'] + 1 > stock:
                    messagebox.showwarning("Stock", "Limit reached!")
                    return
                item['qty'] += 1
                self.update_cart_ui()
                return

        self.cursor.execute("SELECT cost_price FROM products WHERE sku=?", (sku,))
        cost = self.cursor.fetchone()[0]
        
        self.cart.append({'sku': sku, 'title': title, 'price': price, 'cost': cost, 'qty': 1})
        self.update_cart_ui()
        self.search_entry.delete(0, 'end')

    def sync_inventory_from_firebase(self):
        try:
            r = requests.get(f"{FIREBASE_URL}/products.json")
            if r.status_code == 200 and r.json():
                data = r.json()
                items = data.values() if isinstance(data, dict) else [x for x in data if x]
                
                conn = sqlite3.connect('bookshop.db')
                cur = conn.cursor()
                count = 0
                for i in items:
                    if 'sku' not in i: continue
                    cur.execute('''
                        INSERT OR REPLACE INTO products (sku, title, author_supplier, category, product_type, price, cost_price, stock, date_added)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ''', (i.get('sku'), i.get('title'), i.get('author_supplier'), i.get('category'), i.get('product_type'), 
                          float(i.get('price',0)), float(i.get('cost_price',0)), int(i.get('stock',0)), i.get('date_added')))
                    count += 1
                conn.commit()
                conn.close()
                self.root.after(0, self.refresh_inventory)
                print(f"Synced {count} items.")
        except Exception as e: print(f"Sync error: {e}")

    # --- CRUD Wrappers ---
    def reset_form_for_new(self):
        if self.current_role == "Attendant": return
        for k, v in self.inv_entries.items():
            v.config(state='normal')
            if isinstance(v, ttk.Combobox): v.set('')
            else: v.delete(0, 'end')
        self.inv_entries['sku'].config(bg="white")
    
    def on_inventory_select(self, event):
        sel = self.inventory_tree.selection()
        if not sel: return
        vals = self.inventory_tree.item(sel[0])['values']
        self.reset_form_for_new()
        
        self.inv_entries['sku'].insert(0, vals[0])
        self.inv_entries['title'].insert(0, vals[1])
        self.inv_entries['product_type'].set(vals[2])
        self.inv_entries['price'].insert(0, vals[3])
        self.inv_entries['cost_price'].insert(0, vals[4])
        self.inv_entries['stock'].insert(0, vals[5])
        
        res = self.cursor.execute("SELECT author_supplier, category FROM products WHERE sku=?", (vals[0],)).fetchone()
        if res:
            self.inv_entries['author_supplier'].insert(0, res[0])
            self.inv_entries['category'].insert(0, res[1])
        
        self.inv_entries['sku'].config(state='readonly', bg="#cccccc")

    def add_product(self):
        # Implementation similar to original but using dictionary comprehension for cleaner code
        try:
            d = {k: v.get() for k, v in self.inv_entries.items()}
            if not d['sku'] or not d['title']: return
            
            self.cursor.execute("INSERT INTO products (sku, title, author_supplier, category, product_type, price, cost_price, stock, date_added) VALUES (?,?,?,?,?,?,?,?,?)",
                                (d['sku'], d['title'], d['author_supplier'], d['category'], d['product_type'], float(d['price']), float(d['cost_price']), int(d['stock']), datetime.now().strftime('%Y-%m-%d')))
            self.conn.commit()
            
            # Cloud Push
            threading.Thread(target=lambda: requests.put(f"{FIREBASE_URL}/products/{d['sku']}.json", json=d), daemon=True).start()
            
            messagebox.showinfo("Success", "Added")
            self.refresh_inventory()
        except Exception as e: messagebox.showerror("Error", str(e))

    def update_product(self):
        try:
            d = {k: v.get() for k, v in self.inv_entries.items()}
            self.cursor.execute("UPDATE products SET title=?, author_supplier=?, category=?, product_type=?, price=?, cost_price=?, stock=? WHERE sku=?",
                                (d['title'], d['author_supplier'], d['category'], d['product_type'], float(d['price']), float(d['cost_price']), int(d['stock']), d['sku']))
            self.conn.commit()
            threading.Thread(target=lambda: requests.put(f"{FIREBASE_URL}/products/{d['sku']}.json", json=d), daemon=True).start()
            messagebox.showinfo("Success", "Updated")
            self.refresh_inventory()
        except Exception as e: messagebox.showerror("Error", str(e))

    def delete_product(self):
        sku = self.inv_entries['sku'].get()
        if messagebox.askyesno("Confirm", "Delete item?"):
            self.cursor.execute("DELETE FROM products WHERE sku=?", (sku,))
            self.conn.commit()
            threading.Thread(target=lambda: requests.delete(f"{FIREBASE_URL}/products/{sku}.json"), daemon=True).start()
            self.refresh_inventory()

    def refresh_inventory(self):
        self.inventory_tree.delete(*self.inventory_tree.get_children())
        for row in self.cursor.execute("SELECT sku, title, product_type, price, cost_price, stock FROM products"):
            self.inventory_tree.insert('', 'end', values=row)

    # =========================================================================
    # REPORTS LOGIC
    # =========================================================================
    def generate_report(self):
        self.sales_tree.delete(*self.sales_tree.get_children())
        self.reports_text.delete(1.0, 'end')
        
        today = datetime.now().strftime('%Y-%m-%d')
        res_day = self.cursor.execute("SELECT sum(total_amount), sum(discount), sum(total_profit) FROM sales WHERE sale_date LIKE ?", (f'{today}%',)).fetchone()
        res_all = self.cursor.execute("SELECT sum(total_amount), sum(discount), sum(total_profit) FROM sales").fetchone()
        
        # Safe unpacking (handle None)
        day_sales, day_disc, day_profit = [x or 0.0 for x in res_day]
        all_sales, all_disc, all_profit = [x or 0.0 for x in res_all]
        
        rpt = f"📊 PERFORMANCE REPORT\n========================\n"
        rpt += f"TODAY'S REVENUE:   KES {day_sales:,.2f}\n"
        rpt += f"TODAY'S DISCOUNT:  KES {day_disc:,.2f}\n"
        rpt += f"TODAY'S PROFIT:    KES {day_profit:,.2f}\n"
        rpt += "------------------------\n"
        rpt += f"TOTAL REVENUE:     KES {all_sales:,.2f}\n"
        rpt += f"TOTAL DISCOUNT:    KES {all_disc:,.2f}\n"
        rpt += f"TOTAL PROFIT:      KES {all_profit:,.2f}\n"
        
        self.reports_text.insert('end', rpt)
        
        for row in self.cursor.execute("SELECT id, total_amount, discount, sale_date FROM sales ORDER BY id DESC LIMIT 50"):
            self.sales_tree.insert('', 'end', values=row)

    def export_sales_to_csv(self):
        try:
            fname = f"sales_{datetime.now().strftime('%Y%m%d')}.csv"
            with open(fname, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([i[0] for i in self.cursor.description])
                writer.writerows(self.cursor.execute("SELECT * FROM sales"))
            messagebox.showinfo("Export", f"Saved: {fname}")
        except Exception as e: messagebox.showerror("Error", str(e))

    def delete_sale_prompt(self):
        sel = self.sales_tree.selection()
        if not sel: return
        sid = self.sales_tree.item(sel[0])['values'][0]
        
        if messagebox.askyesno("Delete Sale", "Revert stock and delete record?"):
            items = json.loads(self.cursor.execute("SELECT items_json FROM sales WHERE id=?", (sid,)).fetchone()[0])
            for i in items:
                self.cursor.execute("UPDATE products SET stock = stock + ? WHERE sku=?", (i['qty'], i['sku']))
                new_stk = self.cursor.execute("SELECT stock FROM products WHERE sku=?", (i['sku'],)).fetchone()[0]
                threading.Thread(target=lambda s=i['sku'], st=new_stk: requests.patch(f"{FIREBASE_URL}/products/{s}.json", json={"stock": st}), daemon=True).start()
            
            self.cursor.execute("DELETE FROM sales WHERE id=?", (sid,))
            self.conn.commit()
            self.generate_report()
            self.refresh_inventory()

if __name__ == "__main__":
    initialize_database()
    root = tk.Tk()
    LoginWindow(root, lambda u, r: BookshopPOS(root, u, r))
    root.mainloop()

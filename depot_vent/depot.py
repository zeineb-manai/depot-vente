
import tkinter as tk
from tkinter import ttk, messagebox, filedialog, simpledialog
from PIL import Image, ImageTk
import pandas as pd
import os
import uuid
import sqlite3
from datetime import datetime

# =========================================================
# ================ SQLite Persistence =====================
# =========================================================
DB_FILE = "app.db"

def db_conn():
    return sqlite3.connect(DB_FILE)

def init_db():
    """
    Create the SQLite schema for:
      - users: registered users (sellers/buyers)
      - receipts: transaction headers
      - receipt_items: items purchased per receipt
    This persists across runs and is used for reporting + receipts.
    """
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                name TEXT,
                phone TEXT,
                created_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS receipts (
                id TEXT PRIMARY KEY,
                user_id TEXT,           -- the actor who initiated the transaction (buyer or owner)
                role TEXT,              -- 'buyer' or 'owner'
                total REAL,
                created_at TEXT
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS receipt_items (
                receipt_id TEXT,
                item_id TEXT,
                article TEXT,
                depot TEXT,
                price REAL
            )
        """)
        con.commit()

init_db()

# -------------------- Data setup --------------------
FILE_NAME = "items.csv"
# Add UserID to link item to its seller/owner user account
SCHEMA = ["ID", "Depot", "Telephone", "Article", "Price", "Status", "Image", "UserID"]

def ensure_csv_schema():
    """Create CSV if missing. If present, add missing columns safely."""
    if not os.path.exists(FILE_NAME):
        df = pd.DataFrame(columns=SCHEMA)
        df.to_csv(FILE_NAME, index=False)
        return

    df = pd.read_csv(FILE_NAME)
    changed = False

    for col in SCHEMA:
        if col not in df.columns:
            df[col] = ""
            changed = True

    if changed:
        df.to_csv(FILE_NAME, index=False)

ensure_csv_schema()

# -------------------- Utility helpers --------------------
def read_items():
    df = pd.read_csv(FILE_NAME)
    if "Price" in df.columns:
        df["Price"] = pd.to_numeric(df["Price"], errors="coerce").fillna(0.0)
    # Normalize Status values
    if "Status" in df.columns:
        df["Status"] = df["Status"].fillna("").replace({"sold":"Sold","available":"Available"})
    return df

def write_items(df):
    df.to_csv(FILE_NAME, index=False)

def generate_id():
    return str(uuid.uuid4())

def now_iso():
    return datetime.utcnow().isoformat(timespec="seconds")

# =========================================================
# ================ User Management ========================
# =========================================================
def create_user(name, phone):
    """
    Create a new user with a generated UUID. Persist to SQLite.
    """
    uid = generate_id()
    with db_conn() as con:
        con.execute(
            "INSERT INTO users (id, name, phone, created_at) VALUES (?, ?, ?, ?)",
            (uid, name.strip(), phone.strip(), now_iso())
        )
        con.commit()
    return uid

def get_user(user_id):
    if not user_id:
        return None
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, name, phone, created_at FROM users WHERE id = ?", (user_id.strip(),))
        row = cur.fetchone()
        if row:
            return {"id": row[0], "name": row[1], "phone": row[2], "created_at": row[3]}
    return None

def suggest_user_id(name):
    """Suggest user ID based on name if exists"""
    if not name:
        return None
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id FROM users WHERE name = ?", (name.strip(),))
        rows = cur.fetchall()
        return [row[0] for row in rows] if rows else None

def validate_user_id(user_id):
    """Check if user ID exists in database"""
    return bool(get_user(user_id)) if user_id else False

def get_user_dialog(parent, title="Enter Your User ID"):
    """
    Simple dialog that only accepts existing user IDs
    """
    dlg = tk.Toplevel(parent)
    dlg.title(title)
    dlg.geometry("420x180")
    dlg.configure(bg="#EAF6FF")
    dlg.resizable(False, False)
    dlg.transient(parent)
    dlg.grab_set()

    tk.Label(dlg, text="User Login", font=("Arial", 14, "bold"), bg="#EAF6FF").pack(pady=(14, 4))
    
    tk.Label(dlg, text="Enter your User ID:", bg="#EAF6FF", font=("Arial", 11)).pack()
    user_id_var = tk.StringVar()
    e_id = tk.Entry(dlg, textvariable=user_id_var, font=("Arial", 12), width=36)
    e_id.pack(pady=4)

    def submit():
        uid = user_id_var.get().strip()
        if not uid:
            messagebox.showerror("Error", "User ID is required", parent=dlg)
            return
            
        if not validate_user_id(uid):
            messagebox.showerror("Wrong ID", "User ID not found. Please contact owner.", parent=dlg)
            return
            
        dlg.result = uid
        dlg.destroy()

    tk.Button(dlg, text="Login", bg="#1E90FF", fg="white", width=16, command=submit).pack(pady=(6, 10))
    tk.Button(dlg, text="Cancel", bg="#A9A9A9", fg="white", width=12, command=dlg.destroy).pack(pady=4)

    e_id.focus_set()
    parent.wait_window(dlg)
    return getattr(dlg, "result", None)

# =========================================================
# ============ Receipts + Sales History ===================
# =========================================================
def create_receipt(user_id, role, items_rows):
    """
    Persist a receipt and its items.
    items_rows: list of dicts with keys {item_id, article, depot, price}
    Returns receipt_id and total.
    """
    rid = generate_id()
    total = sum(float(x["price"]) for x in items_rows) if items_rows else 0.0
    with db_conn() as con:
        con.execute("INSERT INTO receipts (id, user_id, role, total, created_at) VALUES (?, ?, ?, ?, ?)",
                    (rid, user_id, role, total, now_iso()))
        con.executemany(
            "INSERT INTO receipt_items (receipt_id, item_id, article, depot, price) VALUES (?, ?, ?, ?, ?)",
            [(rid, it["item_id"], it["article"], it["depot"], float(it["price"])) for it in items_rows]
        )
        con.commit()
    return rid, total

def render_receipt_text(receipt_id):
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id, user_id, role, total, created_at FROM receipts WHERE id = ?", (receipt_id,))
        rec = cur.fetchone()
        cur.execute("SELECT item_id, article, depot, price FROM receipt_items WHERE receipt_id = ?", (receipt_id,))
        items = cur.fetchall()

    if not rec:
        return "Receipt not found."
    rid, uid, role, total, created = rec
    header = f"Receipt ID: {rid}\nUser ID: {uid or 'N/A'}\nRole: {role}\nDate: {created}\n\nItems:\n"
    body = ""
    for (item_id, article, depot, price) in items:
        body += f"- {article} (from {depot})  [{item_id}]  -  ${float(price):.2f}\n"
    footer = f"\nTotal: ${float(total):.2f}\n"
    return header + body + footer

# -------------------- Owner UI --------------------
def owner_function():
    pw = tk.Toplevel(window)
    pw.title("Owner Login")
    pw.geometry("420x220")
    pw.configure(bg="#FFE4E1")
    pw.resizable(False, False)

    tk.Label(pw, text="Enter Owner Password", font=("Arial", 18, "bold"),
             bg="#FFE4E1").pack(pady=18)
    entry = tk.Entry(pw, show="*", font=("Arial", 14), width=28)
    entry.pack(pady=5)
    entry.focus_set()

    def do_login():
        if entry.get() == "depot-vente":
            pw.destroy()
            open_owner_dashboard()
        else:
            messagebox.showerror("Error", "Accès refusé", parent=pw)

    tk.Button(pw, text="Login", font=("Arial", 14), bg="#FF69B4", fg="white",
              width=12, height=1, command=do_login).pack(pady=16)

def open_owner_dashboard():
    owner_win = tk.Toplevel(window)
    owner_win.title("Owner Dashboard")
    owner_win.state('zoomed')
    owner_win.configure(bg="#F5F5DC")

    tk.Label(owner_win, text="Owner Dashboard", font=("Arial", 30, "bold"),
             bg="#F5F5DC").pack(pady=10)

    search_frame = tk.Frame(owner_win, bg="#F5F5DC")
    search_frame.pack(pady=5)
    tk.Label(search_frame, text="Filter (Depot/Article):", bg="#F5F5DC",
             font=("Arial", 12)).grid(row=0, column=0, padx=6)
    filter_var = tk.StringVar()
    tk.Entry(search_frame, textvariable=filter_var, font=("Arial", 12), width=32)\
        .grid(row=0, column=1, padx=6)

    table_frame = tk.Frame(owner_win, bg="#FFFFFF", bd=2, relief="sunken")
    table_frame.pack(padx=20, pady=10, fill="both", expand=True)

    columns = ("ID", "Depot", "Telephone", "Article", "Price", "Status", "UserID")
    tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode="extended")
    vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.pack(side="right", fill="y")
    hsb.pack(side="bottom", fill="x")
    tree.pack(fill="both", expand=True)

    for col in columns:
        tree.heading(col, text=col)
    tree.column("ID", width=0, stretch=False)
    tree.column("Depot", width=220)
    tree.column("Telephone", width=180)
    tree.column("Article", width=300)
    tree.column("Price", width=120, anchor="e")
    tree.column("Status", width=120)
    tree.column("UserID", width=280)

    img_frame = tk.Frame(owner_win, bg="#F5F5DC", bd=2, relief="sunken")
    img_frame.pack(side="right", padx=20, pady=10, fill="both", expand=False)
    img_label = tk.Label(img_frame, bg="#F5F5DC")
    img_label.pack(fill="both", expand=True)

    refresh_paused = {"value": False}

    def load_items():
        if refresh_paused["value"]:
            owner_win.after(2000, load_items)
            return
        selected_ids = [tree.item(s)["values"][0] for s in tree.selection()]
        query = filter_var.get().strip().lower()
        tree.delete(*tree.get_children())
        df = read_items()
        if query:
            df = df[
                df["Depot"].astype(str).str.lower().str.contains(query) |
                df["Article"].astype(str).str.lower().str.contains(query)
            ]
        for _, r in df.iterrows():
            tree.insert("", "end", values=(r["ID"], r["Depot"], r["Telephone"], r["Article"], f"{float(r['Price']):.2f}", r["Status"], r.get("UserID","")))
        for i in tree.get_children():
            if tree.item(i)["values"][0] in selected_ids:
                tree.selection_add(i)
        update_image_preview()
        owner_win.after(2000, load_items)

    def with_pause(func):
        def wrapper(*args, **kwargs):
            refresh_paused["value"] = True
            try:
                return func(*args, **kwargs)
            finally:
                refresh_paused["value"] = False
        return wrapper

    @with_pause
    def add_item():
        win = tk.Toplevel(owner_win)
        win.title("Add Item")
        win.geometry("520x580")
        win.configure(bg="#FFF0F5")
        win.resizable(False, False)

        # Name field for UserID suggestion
        tk.Label(win, text="Seller Name (for ID suggestion):", bg="#FFF0F5", font=("Arial", 12)).pack(pady=(10,2))
        name_var = tk.StringVar()
        e_name = tk.Entry(win, textvariable=name_var, font=("Arial", 12), width=40)
        e_name.pack()
        
        # UserID field
        tk.Label(win, text="Seller UserID:", bg="#FFF0F5", font=("Arial", 12)).pack(pady=(10,2))
        user_id_var = tk.StringVar()
        e_user_id = tk.Entry(win, textvariable=user_id_var, font=("Arial", 12), width=40)
        e_user_id.pack()
        
        # Suggest ID from Name
        def suggest_from_name():
            name = name_var.get().strip()
            if not name:
                return
                
            suggested_ids = suggest_user_id(name)
            if not suggested_ids:
                messagebox.showinfo("No Match", "No users found with that name", parent=win)
                return
                
            # Create selection dialog
            sel_win = tk.Toplevel(win)
            sel_win.title("Select User ID")
            sel_win.geometry("400x300")
            sel_win.configure(bg="#F0F8FF")
            
            tk.Label(sel_win, text="Select User ID:", font=("Arial", 12), bg="#F0F8FF").pack(pady=10)
            
            # Create listbox with suggested IDs
            listbox = tk.Listbox(sel_win, font=("Arial", 11), width=50)
            for uid in suggested_ids:
                listbox.insert(tk.END, uid)
            listbox.pack(pady=10, padx=10, fill="both", expand=True)
            
            def select_id():
                selected = listbox.get(listbox.curselection())
                user_id_var.set(selected)
                sel_win.destroy()
            
            tk.Button(sel_win, text="Select", bg="#4B0082", fg="white", 
                      command=select_id).pack(pady=10)
        
        tk.Button(win, text="Suggest IDs from Name", bg="#4B0082", fg="white", 
                  command=suggest_from_name).pack(pady=4)

        # Existing fields
        tk.Label(win, text="Depot", bg="#FFF0F5", font=("Arial", 12)).pack(pady=4)
        e_depot = tk.Entry(win, font=("Arial", 12), width=40); e_depot.pack()

        tk.Label(win, text="Telephone", bg="#FFF0F5", font=("Arial", 12)).pack(pady=4)
        e_tel = tk.Entry(win, font=("Arial", 12), width=40); e_tel.pack()

        tk.Label(win, text="Article", bg="#FFF0F5", font=("Arial", 12)).pack(pady=4)
        e_article = tk.Entry(win, font=("Arial", 12), width=40); e_article.pack()

        tk.Label(win, text="Price", bg="#FFF0F5", font=("Arial", 12)).pack(pady=4)
        e_price = tk.Entry(win, font=("Arial", 12), width=40); e_price.pack()

        img_path_var = tk.StringVar()
        def browse_image():
            path = filedialog.askopenfilename(
                parent=win,
                filetypes=[("Image Files", "*.png;*.jpg;*.jpeg;*.gif")]
            )
            if path:
                img_path_var.set(path)

        tk.Button(win, text="Browse Image", bg="#1E90FF", fg="white", command=browse_image).pack(pady=8)

        def save():
            # Validate UserID if provided
            user_id_val = user_id_var.get().strip()
            if user_id_val and not validate_user_id(user_id_val):
                messagebox.showerror("Error", "Seller UserID does not exist. Please enter a valid ID.", parent=win)
                return
                
            try:
                price = float(e_price.get())
            except ValueError:
                messagebox.showerror("Error", "Price must be a number", parent=win)
                return
            df = read_items()
            new_row = {
                "ID": generate_id(),
                "Depot": e_depot.get().strip(),
                "Telephone": e_tel.get().strip(),
                "Article": e_article.get().strip(),
                "Price": price,
                "Status": "Available",
                "Image": img_path_var.get(),
                "UserID": user_id_val
            }
            df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)
            write_items(df)
            win.destroy()

        tk.Button(win, text="Save", font=("Arial", 12), bg="#FF69B4", fg="white", width=14, command=save).pack(pady=14)

    def update_image_preview(event=None):
        sel = tree.selection()
        if sel:
            item_id = tree.item(sel[0])["values"][0]
            df = read_items()
            img_path = str(df.loc[df["ID"] == item_id, "Image"].values[0]) if len(df.loc[df["ID"] == item_id, "Image"]) else ""
            if img_path and str(img_path).lower() != "nan" and os.path.exists(img_path):
                img = Image.open(img_path)
                img = img.resize((300, 300), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                img_label.image = img_tk
                img_label.config(image=img_tk, text="")
                def open_fullscreen(e=None):
                    fs_win = tk.Toplevel(owner_win)
                    fs_win.title("Image Fullscreen")
                    fs_win.configure(bg="black")
                    fs_img = ImageTk.PhotoImage(Image.open(img_path))
                    lbl = tk.Label(fs_win, image=fs_img, bg="black")
                    lbl.image = fs_img
                    lbl.pack(expand=True, fill="both")
                    fs_win.bind("<Escape>", lambda e: fs_win.destroy())
                    tk.Button(fs_win, text="Close", command=fs_win.destroy, bg="#A9A9A9", fg="white").pack(side="bottom", pady=8)
                img_label.bind("<Button-1>", open_fullscreen)
            else:
                img_label.config(image="", text="No photo available")
        else:
            img_label.config(image="", text="No photo available")

    @with_pause
    def modify_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Error", "Select one item to modify", parent=owner_win)
            return
        if len(sel) > 1:
            messagebox.showerror("Error", "Select only one item to modify", parent=owner_win)
            return
        item = tree.item(sel[0])["values"]
        item_id, depot, tel, article, price, status, user_id_val = item
        df = read_items()
        img_path = df.loc[df["ID"] == item_id, "Image"].values[0]

        win = tk.Toplevel(owner_win)
        win.title("Modify Item")
        win.geometry("520x640")
        win.configure(bg="#FFF8E7")
        win.resizable(False, False)

        # Name field for UserID suggestion
        tk.Label(win, text="Seller Name (for ID suggestion):", bg="#FFF8E7", font=("Arial", 12)).pack(pady=4)
        name_var = tk.StringVar()
        e_name = tk.Entry(win, textvariable=name_var, font=("Arial", 12), width=40)
        e_name.pack()
        
        # UserID field
        tk.Label(win, text="UserID (seller):", bg="#FFF8E7", font=("Arial", 12)).pack(pady=4)
        e_user = tk.Entry(win, font=("Arial", 12), width=40)
        e_user.insert(0, user_id_val)
        e_user.pack()
        
        # Suggest ID from Name
        def suggest_from_name():
            name = name_var.get().strip()
            if not name:
                return
                
            suggested_ids = suggest_user_id(name)
            if not suggested_ids:
                messagebox.showinfo("No Match", "No users found with that name", parent=win)
                return
                
            # Create selection dialog
            sel_win = tk.Toplevel(win)
            sel_win.title("Select User ID")
            sel_win.geometry("400x300")
            sel_win.configure(bg="#F0F8FF")
            
            tk.Label(sel_win, text="Select User ID:", font=("Arial", 12), bg="#F0F8FF").pack(pady=10)
            
            # Create listbox with suggested IDs
            listbox = tk.Listbox(sel_win, font=("Arial", 11), width=50)
            for uid in suggested_ids:
                listbox.insert(tk.END, uid)
            listbox.pack(pady=10, padx=10, fill="both", expand=True)
            
            def select_id():
                selected = listbox.get(listbox.curselection())
                e_user.delete(0, tk.END)
                e_user.insert(0, selected)
                sel_win.destroy()
            
            tk.Button(sel_win, text="Select", bg="#4B0082", fg="white", 
                      command=select_id).pack(pady=10)
        
        tk.Button(win, text="Suggest IDs from Name", bg="#4B0082", fg="white", 
                  command=suggest_from_name).pack(pady=4)

        # Existing fields
        def add_row(label, initial=""):
            tk.Label(win, text=label, bg="#FFF8E7", font=("Arial", 12)).pack(pady=4)
            ent = tk.Entry(win, font=("Arial", 12), width=40)
            ent.insert(0, str(initial))
            ent.pack()
            return ent

        e_depot = add_row("Depot", depot)
        e_tel = add_row("Telephone", tel)
        e_article = add_row("Article", article)
        e_price = add_row("Price", price)
        e_status = add_row("Status (Available/Sold)", status)
        img_path_var = tk.StringVar(value=img_path)
        def browse_image():
            path = filedialog.askopenfilename(
                parent=win,
                filetypes=[("Image Files","*.png;*.jpg;*.jpeg;*.gif")]
            )
            if path:
                img_path_var.set(path)

        tk.Button(win, text="Browse Image", bg="#1E90FF", fg="white", command=browse_image).pack(pady=8)

        def save_changes():
            # Validate UserID if provided
            user_id_val = e_user.get().strip()
            if user_id_val and not validate_user_id(user_id_val):
                messagebox.showerror("Error", "Seller UserID does not exist. Please enter a valid ID.", parent=win)
                return
                
            try:
                new_price = float(e_price.get())
            except ValueError:
                messagebox.showerror("Error", "Price must be a number", parent=win)
                return
            new_status = e_status.get().strip() or "Available"
            if new_status not in ("Available", "Sold"):
                messagebox.showerror("Error", "Status must be 'Available' or 'Sold'", parent=win)
                return
            df = read_items()
            idx = df.index[df["ID"] == item_id]
            if len(idx):
                ix = idx[0]
                df.loc[ix, "UserID"] = user_id_val
                df.loc[ix, "Depot"] = e_depot.get().strip()
                df.loc[ix, "Telephone"] = e_tel.get().strip()
                df.loc[ix, "Article"] = e_article.get().strip()
                df.loc[ix, "Price"] = new_price
                df.loc[ix, "Status"] = new_status
                df.loc[ix, "Image"] = img_path_var.get()
                write_items(df)
            win.destroy()

        tk.Button(win, text="Save Changes", font=("Arial", 12),
                  bg="#FFD700", fg="#000", width=16, command=save_changes).pack(pady=16)

    def delete_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Error", "Select item(s) to delete", parent=owner_win)
            return
        if not messagebox.askyesno("Confirm", "Delete selected item(s)? This does not affect receipts history.", parent=owner_win):
            return
        ids = [tree.item(s)["values"][0] for s in sel]
        df = read_items()
        df = df[~df["ID"].isin(ids)]
        write_items(df)

    def mark_sold():
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Error", "Select item(s) to mark as sold", parent=owner_win)
            return
        # Ask for buyer (must be existing)
        buyer_id = get_user_dialog(owner_win, title="Buyer ID (for receipt)")
        if buyer_id is None:
            return

        df = read_items()
        ids = [tree.item(s)["values"][0] for s in sel]
        items_rows = []
        for s in sel:
            vals = tree.item(s)["values"]
            items_rows.append({
                "item_id": vals[0],
                "depot": vals[1],
                "article": vals[3],
                "price": float(vals[4])
            })
        # Create receipt for buyer; owner executed action (role='owner')
        receipt_id, total = create_receipt(buyer_id, role="owner", items_rows=items_rows)
        df.loc[df["ID"].isin(ids), "Status"] = "Sold"
        write_items(df)
        # Show receipt
        rec_txt = render_receipt_text(receipt_id)
        messagebox.showinfo("Items Sold", f"Receipt created.\n\n{rec_txt}", parent=owner_win)

    def calculate_total_25():
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Error", "Select item(s) to calculate", parent=owner_win)
            return
        prices = [float(tree.item(s)["values"][4]) for s in sel]
        total = sum(prices)
        depot_share = total * 0.25
        final_total = total - depot_share

        receipt_text = "Receipt (Depot Gain 25%)\n\n"
        for s in sel:
            item = tree.item(s)["values"]
            receipt_text += f"{item[3]} (from {item[1]})  -  ${float(item[4]):.2f}\n"
        receipt_text += f"\nOriginal Total: ${total:.2f}"
        receipt_text += f"\nDepot Share (25%): ${depot_share:.2f}"
        receipt_text += f"\nNet Total: ${final_total:.2f}"

        rec = tk.Toplevel(owner_win)
        rec.title("Receipt")
        rec.geometry("460x420")
        rec.configure(bg="#FFF8DC")
        tk.Label(rec, text="Receipt", font=("Arial", 20, "bold"), bg="#FFF8DC").pack(pady=10)
        txt = tk.Text(rec, font=("Arial", 12), bg="#FFF8DC", wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=8)
        txt.insert("1.0", receipt_text)
        txt.config(state="disabled")
        tk.Button(rec, text="Close", font=("Arial", 12),
                  bg="#A9A9A9", fg="white", width=12, command=rec.destroy).pack(pady=10)

    def calculate_25_percent():
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Error", "Select item(s) to calculate 25% of", parent=owner_win)
            return
        prices = [float(tree.item(s)["values"][4]) for s in sel]
        total = sum(prices)
        gained = total * 0.25
        messagebox.showinfo("25% Calculation", f"Total of selected items: ${total:.2f}\n25% Gain: ${gained:.2f}", parent=owner_win)
        
    def manage_users():
        """Owner can add users in this section"""
        users_win = tk.Toplevel(owner_win)
        users_win.title("Manage Users")
        users_win.geometry("600x400")
        users_win.configure(bg="#F5F5DC")

        tk.Label(users_win, text="User Management", font=("Arial", 20, "bold"), 
                 bg="#F5F5DC").pack(pady=10)

        # Treeview for users
        columns = ("ID", "Name", "Phone", "Created")
        tree = ttk.Treeview(users_win, columns=columns, show='headings')
        vsb = ttk.Scrollbar(users_win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        
        for col in columns:
            tree.heading(col, text=col)
        tree.column("ID", width=200)
        tree.column("Name", width=150)
        tree.column("Phone", width=120)
        tree.column("Created", width=150)
        
        vsb.pack(side="right", fill="y")
        tree.pack(fill="both", expand=True, padx=10, pady=5)

        def load_users():
            tree.delete(*tree.get_children())
            with db_conn() as con:
                cur = con.cursor()
                cur.execute("SELECT id, name, phone, created_at FROM users")
                for row in cur.fetchall():
                    tree.insert("", "end", values=row)
        
        load_users()

        # Add user section
        add_frame = tk.Frame(users_win, bg="#F5F5DC")
        add_frame.pack(fill="x", padx=10, pady=10)
        
        tk.Label(add_frame, text="Name:", bg="#F5F5DC").grid(row=0, column=0, padx=2)
        name_var = tk.StringVar()
        tk.Entry(add_frame, textvariable=name_var, width=20).grid(row=0, column=1, padx=2)
        
        tk.Label(add_frame, text="Phone:", bg="#F5F5DC").grid(row=0, column=2, padx=2)
        phone_var = tk.StringVar()
        tk.Entry(add_frame, textvariable=phone_var, width=15).grid(row=0, column=3, padx=2)
        
        def add_user():
            name = name_var.get().strip()
            phone = phone_var.get().strip()
            if not name:
                messagebox.showerror("Error", "Name is required", parent=users_win)
                return
                
            uid = create_user(name, phone)
            messagebox.showinfo("Success", f"User created with ID:\n\n{uid}", parent=users_win)
            load_users()
        
        tk.Button(add_frame, text="Add User", bg="#32CD32", fg="white", 
                  command=add_user).grid(row=0, column=4, padx=10)
        
        tk.Button(users_win, text="Close", bg="#A9A9A9", fg="white", 
                  command=users_win.destroy).pack(pady=10)

    btn = tk.Frame(owner_win, bg="#F5F5DC")
    btn.pack(pady=10)
    tk.Button(btn, text="Add Item", width=18, height=2, bg="#FF69B4", fg="#FFFFFF",
              font=("Arial", 13), command=add_item).grid(row=0, column=0, padx=8, pady=6)
    tk.Button(btn, text="Modify Selected", width=18, height=2, bg="#FFD700", fg="#000000",
              font=("Arial", 13), command=modify_selected).grid(row=0, column=1, padx=8, pady=6)
    tk.Button(btn, text="Delete Selected", width=18, height=2, bg="#FF6347", fg="#FFFFFF",
              font=("Arial", 13), command=delete_selected).grid(row=0, column=2, padx=8, pady=6)
    tk.Button(btn, text="Mark Sold", width=18, height=2, bg="#32CD32", fg="#FFFFFF",
              font=("Arial", 13), command=mark_sold).grid(row=0, column=3, padx=8, pady=6)
    tk.Button(btn, text="Depot 25% Total", width=18, height=2, bg="#8A2BE2", fg="#FFFFFF",
              font=("Arial", 13), command=calculate_total_25).grid(row=0, column=4, padx=8, pady=6)
    tk.Button(btn, text="Calculate 25% Gain", width=18, height=2, bg="#1E90FF", fg="#FFFFFF",
              font=("Arial", 13), command=calculate_25_percent).grid(row=0, column=5, padx=8, pady=6)
    tk.Button(btn, text="Manage Users", width=18, height=2, bg="#9370DB", fg="#FFFFFF",
              font=("Arial", 13), command=manage_users).grid(row=0, column=6, padx=8, pady=6)
    tk.Button(btn, text="Exit", width=18, height=2, bg="#A9A9A9", fg="#FFFFFF",
              font=("Arial", 13), command=owner_win.destroy).grid(row=0, column=7, padx=8, pady=6)

    load_items()

# -------------------- Buyer UI --------------------
def buyer_function():
    buyer_win = tk.Toplevel(window)
    buyer_win.title("Buyer Dashboard")
    buyer_win.state("zoomed")
    buyer_win.configure(bg="#FFC0CB")  # Pink theme

    tk.Label(buyer_win, text="Buyer Dashboard", font=("Arial", 30, "bold"),
             bg="#FFC0CB").pack(pady=12)

    # Search Frame
    search_frame = tk.Frame(buyer_win, bg="#FFC0CB")
    search_frame.pack(pady=5)
    tk.Label(search_frame, text="Search Article/Depot:", font=("Arial", 12),
             bg="#FFC0CB").grid(row=0, column=0, padx=6)
    search_var = tk.StringVar()
    search_entry = tk.Entry(search_frame, font=("Arial", 12), width=32, textvariable=search_var)
    search_entry.grid(row=0, column=1, padx=6)

    # Table Frame
    table_frame = tk.Frame(buyer_win, bg="#FFFFFF", bd=2, relief="sunken")
    table_frame.pack(padx=20, pady=10, fill="both", expand=True)

    columns = ("ID", "Depot", "Telephone", "Article", "Price", "Status")
    tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode="extended")
    vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.pack(side="right", fill="y")
    hsb.pack(side="bottom", fill="x")
    tree.pack(fill="both", expand=True)

    for col in columns:
        tree.heading(col, text=col)
    tree.column("ID", width=0, stretch=False)
    tree.column("Depot", width=200)
    tree.column("Telephone", width=150)
    tree.column("Article", width=280)
    tree.column("Price", width=120, anchor="e")
    tree.column("Status", width=120)

    # Image preview frame
    img_frame = tk.Frame(buyer_win, bg="#FFC0CB", bd=2, relief="sunken")
    img_frame.pack(side="right", padx=20, pady=10, fill="both", expand=False)
    img_label = tk.Label(img_frame, bg="#FFC0CB")
    img_label.pack(fill="both", expand=True)

    refresh_paused = {"value": False}

    def load_buyer_items():
        if refresh_paused["value"]:
            buyer_win.after(2000, load_buyer_items)
            return
        selected_ids = [tree.item(s)["values"][0] for s in tree.selection()]
        query = search_var.get().strip().lower()
        tree.delete(*tree.get_children())
        df = read_items()
        df = df[df["Status"] == "Available"]  # Only show available items
        if query:
            df = df[
                df["Depot"].astype(str).str.lower().str.contains(query) |
                df["Article"].astype(str).str.lower().str.contains(query)
            ]
        for _, r in df.iterrows():
            tree.insert("", "end", values=(r["ID"], r["Depot"], r["Telephone"], r["Article"],
                                           f"{float(r['Price']):.2f}", r["Status"]))
        for i in tree.get_children():
            if tree.item(i)["values"][0] in selected_ids:
                tree.selection_add(i)
        update_image_preview()
        buyer_win.after(2000, load_buyer_items)

    def with_pause(func):
        def wrapper(*args, **kwargs):
            refresh_paused["value"] = True
            try:
                return func(*args, **kwargs)
            finally:
                refresh_paused["value"] = False
        return wrapper

    def update_image_preview(event=None):
        sel = tree.selection()
        if sel:
            item_id = tree.item(sel[0])["values"][0]
            df = read_items()
            img_path = str(df.loc[df["ID"] == item_id, "Image"].values[0]) if len(df.loc[df["ID"] == item_id, "Image"]) else ""
            if img_path and img_path.lower() != "nan" and os.path.exists(img_path):
                img = Image.open(img_path)
                img = img.resize((300, 300), Image.LANCZOS)
                img_tk = ImageTk.PhotoImage(img)
                img_label.config(image=img_tk, text="")
                img_label.image = img_tk
            else:
                img_label.config(image="", text="No photo available")
                img_label.image = None
        else:
            img_label.config(image="", text="No photo available")
            img_label.image = None

    tree.bind("<<TreeviewSelect>>", update_image_preview)

    @with_pause
    def buy_selected():
        sel = tree.selection()
        if not sel:
            messagebox.showerror("Error", "Select item(s) to buy", parent=buyer_win)
            return

        # Prompt buyer to enter existing ID
        buyer_id = get_user_dialog(buyer_win, title="Buyer ID")
        if buyer_id is None:
            return

        df = read_items()
        items_rows = []
        ids_to_update = []
        for s in sel:
            item = tree.item(s)["values"]
            ids_to_update.append(item[0])
            items_rows.append({"item_id": item[0], "article": item[3], "depot": item[1], "price": float(item[4])})

        # Persist receipt (role='buyer') before marking as sold
        receipt_id, total = create_receipt(buyer_id, role="buyer", items_rows=items_rows)
        df.loc[df["ID"].isin(ids_to_update), "Status"] = "Sold"
        write_items(df)

        # Show receipt with buyer ID and details
        rec = tk.Toplevel(buyer_win)
        rec.title("Receipt")
        rec.geometry("520x480")
        rec.configure(bg="#FFF0F5")
        tk.Label(rec, text="Receipt", font=("Arial", 20, "bold"), bg="#FFF0F5").pack(pady=10)
        txt = tk.Text(rec, font=("Arial", 12), bg="#FFF0F5", wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=8)
        txt.insert("1.0", render_receipt_text(receipt_id))
        txt.config(state="disabled")
        tk.Button(rec, text="Close", font=("Arial", 12),
                  bg="#A9A9A9", fg="white", width=12, command=rec.destroy).pack(pady=10)

    btn_frame = tk.Frame(buyer_win, bg="#FFC0CB")
    btn_frame.pack(pady=10)
    tk.Button(btn_frame, text="Buy Selected", width=18, height=2, bg="#FF69B4", fg="white",
              font=("Arial", 13), command=buy_selected).grid(row=0, column=0, padx=8, pady=6)
    tk.Button(btn_frame, text="Exit", width=18, height=2, bg="#A9A9A9", fg="white",
              font=("Arial", 13), command=buyer_win.destroy).grid(row=0, column=1, padx=8, pady=6)

    load_buyer_items()

# =========================================================
# ===== User Portal (Seller inventory management) =========
# =========================================================
def user_portal():
    """
    Sellers can log in with their User ID to view ONLY their items
    """
    uid = get_user_dialog(window, title="User Portal - Enter User ID")
    if not uid:
        return
    u = get_user(uid)
    if not u:
        messagebox.showerror("Error", "User not found.", parent=window)
        return

    up = tk.Toplevel(window)
    up.title(f"User Portal - {u['name'] or uid}")
    up.state("zoomed")
    up.configure(bg="#EEF9F3")

    tk.Label(up, text=f"User Portal - {u['name'] or 'Unnamed'}", font=("Arial", 28, "bold"), bg="#EEF9F3").pack(pady=12)

    # Filter and table
    search_frame = tk.Frame(up, bg="#EEF9F3")
    search_frame.pack(pady=5)
    tk.Label(search_frame, text="Search Article:", font=("Arial", 12), bg="#EEF9F3").grid(row=0, column=0, padx=6)
    search_var = tk.StringVar()
    tk.Entry(search_frame, textvariable=search_var, font=("Arial", 12), width=32).grid(row=0, column=1, padx=6)

    table_frame = tk.Frame(up, bg="#FFFFFF", bd=2, relief="sunken")
    table_frame.pack(padx=20, pady=10, fill="both", expand=True)

    columns = ("ID","Article","Price","Status")
    tree = ttk.Treeview(table_frame, columns=columns, show='headings', selectmode="extended")
    for col in columns:
        tree.heading(col, text=col)
    tree.column("ID", width=0, stretch=False)
    tree.column("Article", width=380)
    tree.column("Price", width=120, anchor="e")
    tree.column("Status", width=120)
    vsb = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
    hsb = ttk.Scrollbar(table_frame, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
    vsb.pack(side="right", fill="y")
    hsb.pack(side="bottom", fill="x")
    tree.pack(fill="both", expand=True)

    def load_my_items():
        tree.delete(*tree.get_children())
        df = read_items()
        df = df[df["UserID"].astype(str) == uid]
        q = search_var.get().strip().lower()
        if q:
            df = df[df["Article"].astype(str).str.lower().str.contains(q)]
        for _, r in df.iterrows():
            tree.insert("", "end", values=(r["ID"], r["Article"], f"{float(r['Price']):.2f}", r["Status"]))

    def my_report():
        df = read_items()
        mine = df[df["UserID"].astype(str) == uid]
        sold = mine[mine["Status"] == "Sold"]
        available = mine[mine["Status"] == "Available"]

        total_items = len(mine)
        sold_count = len(sold)
        remaining_count = len(available)
        total_sales_amount = float(sold["Price"].sum())
        seller_income = total_sales_amount * 0.75  # 25% depot, 75% to seller

        # Show report
        rep = tk.Toplevel(up)
        rep.title("My Report")
        rep.geometry("520x520")
        rep.configure(bg="#F7FFF1")

        summary = (
            f"User: {u['name'] or ''} ({uid})\n"
            f"Phone: {u['phone'] or ''}\n"
            f"Created: {u['created_at']}\n\n"
            f"Total Items Listed: {total_items}\n"
            f"Items Sold: {sold_count}\n"
            f"Items Remaining: {remaining_count}\n"
            f"Gross Sales: ${total_sales_amount:.2f}\n"
            f"Estimated Income (75%): ${seller_income:.2f}\n"
        )
        tk.Label(rep, text="My Inventory Report", font=("Arial", 18, "bold"), bg="#F7FFF1").pack(pady=10)
        txt = tk.Text(rep, font=("Arial", 12), bg="#F7FFF1", wrap="word")
        txt.pack(fill="both", expand=True, padx=10, pady=8)
        txt.insert("1.0", summary + "\nSold Items:\n")
        for _, r in sold.iterrows():
            txt.insert("end", f"- {r['Article']} | ${float(r['Price']):.2f}\n")
        txt.insert("end", "\nAvailable Items:\n")
        for _, r in available.iterrows():
            txt.insert("end", f"- {r['Article']} | ${float(r['Price']):.2f}\n")
        txt.config(state="disabled")

        # Historical receipts affecting this user (as buyer)
        with db_conn() as con:
            cur = con.cursor()
            cur.execute("SELECT id FROM receipts WHERE user_id = ? ORDER BY created_at DESC", (uid,))
            rows = cur.fetchall()
        if rows:
            tk.Label(rep, text="\nMy Historical Receipts (as actor):", font=("Arial", 14, "bold"), bg="#F7FFF1").pack()
            hist = tk.Text(rep, font=("Arial", 11), bg="#F7FFF1", height=10, wrap="word")
            hist.pack(fill="both", expand=False, padx=10, pady=6)
            for (rid,) in rows:
                hist.insert("end", render_receipt_text(rid) + "\n" + "-"*40 + "\n")
            hist.config(state="disabled")

        tk.Button(rep, text="Close", bg="#A9A9A9", fg="white", command=rep.destroy).pack(pady=8)

    # Buttons
    btn = tk.Frame(up, bg="#EEF9F3")
    btn.pack(pady=10)
    tk.Button(btn, text="My Report", width=16, height=2, bg="#2E8B57", fg="white",
              font=("Arial", 12), command=my_report).grid(row=0, column=0, padx=8, pady=6)
    tk.Button(btn, text="Close", width=16, height=2, bg="#A9A9A9", fg="white",
              font=("Arial", 12), command=up.destroy).grid(row=0, column=1, padx=8, pady=6)

    search_var.trace_add("write", lambda *_: load_my_items())
    load_my_items()

# =========================================================
# ============== Reports (by any User ID) =================
# =========================================================
def reports_by_user():
    """
    Prompt for any UserID and show their inventory + counts + income
    """
    uid = get_user_dialog(window, title="Reports - Enter User ID")
    if not uid:
        return
    u = get_user(uid)
    df = read_items()
    mine = df[df["UserID"].astype(str) == uid]
    sold = mine[mine["Status"] == "Sold"]
    available = mine[mine["Status"] == "Available"]

    total_items = len(mine)
    sold_count = len(sold)
    remaining_count = len(available)
    total_sales_amount = float(sold["Price"].sum())
    seller_income = total_sales_amount * 0.75

    rep = tk.Toplevel(window)
    rep.title("User Report")
    rep.geometry("560x560")
    rep.configure(bg="#FAFFF6")

    tk.Label(rep, text="User Report", font=("Arial", 22, "bold"), bg="#FAFFF6").pack(pady=10)
    summary = (
        f"User: {(u and u.get('name')) or ''} ({uid})\n"
        f"Phone: {(u and u.get('phone')) or ''}\n"
        f"Created: {(u and u.get('created_at')) or ''}\n\n"
        f"Total Items Listed: {total_items}\n"
        f"Items Sold: {sold_count}\n"
        f"Items Remaining: {remaining_count}\n"
        f"Gross Sales: ${total_sales_amount:.2f}\n"
        f"Estimated Income (75%): ${seller_income:.2f}\n"
    )
    txt = tk.Text(rep, font=("Arial", 12), bg="#FAFFF6", wrap="word")
    txt.pack(fill="both", expand=True, padx=12, pady=10)
    txt.insert("1.0", summary + "\nItems in Inventory:\n")
    for _, r in mine.iterrows():
        txt.insert("end", f"- [{r['Status']}] {r['Article']} | ${float(r['Price']):.2f}\n")
    txt.insert("end", "\nHistorical Receipts (as actor):\n")
    with db_conn() as con:
        cur = con.cursor()
        cur.execute("SELECT id FROM receipts WHERE user_id = ? ORDER BY created_at DESC", (uid,))
        rows = cur.fetchall()
    if rows:
        for (rid,) in rows:
            txt.insert("end", render_receipt_text(rid) + "\n" + "-"*40 + "\n")
    else:
        txt.insert("end", "None\n")
    txt.config(state="disabled")

    tk.Button(rep, text="Close", bg="#A9A9A9", fg="white", command=rep.destroy).pack(pady=8)

# =========================================================
# ================= Main Window + Menus ===================
# =========================================================
window = tk.Tk()
window.title("Depot-Vente System")
window.state("zoomed")
window.configure(bg="#FFF0F5")
window.resizable(False, False)

# Menu-driven interface
menubar = tk.Menu(window)
m_user = tk.Menu(menubar, tearoff=0)
m_user.add_command(label="User Portal (View My Inventory)", command=user_portal)
m_user.add_command(label="Reports (by User ID)", command=reports_by_user)
menubar.add_cascade(label="User", menu=m_user)

m_owner = tk.Menu(menubar, tearoff=0)
m_owner.add_command(label="Owner Login", command=owner_function)
menubar.add_cascade(label="Owner", menu=m_owner)

m_buyer = tk.Menu(menubar, tearoff=0)
m_buyer.add_command(label="Buyer Dashboard", command=buyer_function)
menubar.add_cascade(label="Buyer", menu=m_buyer)

m_help = tk.Menu(menubar, tearoff=0)
m_help.add_command(label="About", command=lambda: messagebox.showinfo("About",
    "Depot-Vente System with Users, Receipts, and Reports.\nData: items.csv + app.db"))
menubar.add_cascade(label="Help", menu=m_help)

window.config(menu=menubar)

tk.Label(window, text="Depot-Vente Management", font=("Arial", 28, "bold"), bg="#FFF0F5").pack(pady=40)

# Quick-access buttons
tk.Button(window, text="Owner Login", font=("Arial", 16), width=18, height=2, bg="#FF69B4", fg="white", command=owner_function).pack(pady=10)
tk.Button(window, text="Buyer Access", font=("Arial", 16), width=18, height=2, bg="#1E90FF", fg="white", command=buyer_function).pack(pady=10)
tk.Button(window, text="User Portal", font=("Arial", 16), width=18, height=2, bg="#7B68EE", fg="white", command=user_portal).pack(pady=10)

window.mainloop()
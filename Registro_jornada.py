from flask import Flask, render_template, request, redirect, send_file, abort
from flask_login import LoginManager, login_user, login_required, logout_user, current_user, UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
import sqlite3, csv
from datetime import datetime
import webbrowser
import threading
# PDF
from reportlab.platypus import Image
import os

from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
#===================================================
#         DEFINIR RUTA DE SALIDA GRABAR RESULTADOS
#==================================================
import os
from pathlib import Path

def carpeta_empresa(nombre_usuario):
    hoy = datetime.now()

    año = hoy.strftime("%Y")
    mes_num = hoy.strftime("%m")
    mes_nombre = hoy.strftime("%B").capitalize()

    base = Path.home() / "RegistroJornada"
    ruta = base / año / f"{mes_num}_{mes_nombre}" / nombre_usuario

    ruta.mkdir(parents=True, exist_ok=True)
    return ruta


# =====================================================
# APP
# =====================================================
app = Flask(__name__)
app.secret_key = "registro-jornada"

login_manager = LoginManager(app)
login_manager.login_view = "/"

DATABASE = "database.db"


# =====================================================
# DB
# =====================================================
def db():
    return sqlite3.connect(DATABASE)


def init_db():
    con = db()
    c = con.cursor()

    # ----------------------------
    # TABLA USUARIOS
    # ----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS users(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        is_admin INTEGER,
        activo INTEGER DEFAULT 1
    )
    """)

    # ----------------------------
    # TABLA FICHAJES
    # ----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS fichajes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        tipo TEXT,
        fecha TEXT
    )
    """)

    # ----------------------------
    # TABLA AUDITORÍA (NUEVA)
    # ----------------------------
    c.execute("""
    CREATE TABLE IF NOT EXISTS auditoria(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        admin TEXT,
        usuario TEXT,
        fichaje_id INTEGER,
        fecha_original TEXT,
        fecha_nueva TEXT,
        motivo TEXT,
        timestamp TEXT
    )
    """)

    # ----------------------------
    # CREAR ADMIN SI NO EXISTE
    # ----------------------------
    c.execute("SELECT id FROM users WHERE is_admin=1")
    if not c.fetchone():
        c.execute(
            "INSERT INTO users (username,password,is_admin,activo) VALUES (?,?,1,1)",
            ("admin", generate_password_hash("admin"))
        )

    # ----------------------------
    # PROTEGER ADMIN
    # ----------------------------
    c.execute("""
    CREATE TRIGGER IF NOT EXISTS prevent_disable_admin
    BEFORE UPDATE OF activo ON users
    WHEN OLD.is_admin = 1 AND NEW.activo = 0
    BEGIN
        SELECT RAISE(ABORT, 'No se puede desactivar un administrador');
    END;
    """)

    con.commit()
    con.close()
init_db()

#=====================================================
#          AUDITORIA
#=====================================================
@app.route("/auditoria")
@login_required
def auditoria():

    if not current_user.is_admin:
        return redirect("/dashboard")

    con = db()
    c = con.cursor()

    c.execute("""
        SELECT admin, usuario, fecha_original, fecha_nueva, motivo, timestamp
        FROM auditoria
        ORDER BY id DESC
    """)

    logs = c.fetchall()
    con.close()

    return render_template("auditoria.html", logs=logs)


# =====================================================
# USER
# =====================================================
class User(UserMixin):
    def __init__(self, id, username, is_admin):
        self.id = id
        self.username = username
        self.is_admin = is_admin


@login_manager.user_loader
def load_user(user_id):
    con = db()
    c = con.cursor()
    c.execute("SELECT id, username, is_admin FROM users WHERE id=?", (user_id,))
    r = c.fetchone()
    con.close()
    if r:
        return User(*r)


# =====================================================
# LOGIN
# =====================================================
@app.route("/", methods=["GET", "POST"])
def login():
    error = None
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        con = db()
        c = con.cursor()
        c.execute(
            "SELECT id, username, password, is_admin, activo FROM users WHERE username=?",
            (u,)
        )
        r = c.fetchone()
        con.close()

        if r and check_password_hash(r[2], p) and r[4] == 1:
            login_user(User(r[0], r[1], r[3]))
            return redirect("/dashboard")
        else:
            error = "Usuario o contraseña es errónea"

    return render_template("login.html", error=error)


@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect("/")


# =====================================================
# DASHBOARD
# =====================================================
@app.route("/dashboard")
@login_required
def dashboard():

    con = db()
    c = con.cursor()
    c.execute(
        "SELECT tipo, fecha FROM fichajes WHERE user_id=? ORDER BY fecha ASC",
        (current_user.id,)
    )
    fichajes = c.fetchall()
    con.close()

    estado = "fuera"
    if fichajes and fichajes[-1][0] == "entrada":
        estado = "dentro"

    jornadas = []
    entrada = None
    total_horas = 0

    for tipo, fecha in fichajes:
        momento = datetime.strptime(fecha, "%d/%m/%Y %H:%M:%S")

        if tipo == "entrada":
            entrada = momento

        elif tipo == "salida" and entrada:
            diff = momento - entrada
            horas = round(diff.total_seconds()/3600, 2)
            total_horas += horas

            jornadas.append((
                entrada.strftime("%d/%m/%Y %H:%M"),
                momento.strftime("%d/%m/%Y %H:%M"),
                horas
            ))
            entrada = None

    return render_template(
        "dashboard.html",
        fichajes=reversed(fichajes),
        estado=estado,
        jornadas=jornadas,
        total_horas=round(total_horas,2)
    )

# =====================================================
# ADMIN
# =====================================================
@app.route("/admin")
@login_required
def admin():

    if not current_user.is_admin:
        return redirect("/dashboard")

    con = db()
    c = con.cursor()
    c.execute("SELECT id, username, activo FROM users")
    users = c.fetchall()
    con.close()

    return render_template("admin.html", users=users)


@app.route("/crear_usuario", methods=["GET","POST"])
@login_required
def crear_usuario():

    if not current_user.is_admin:
        return redirect("/dashboard")

    error=None

    if request.method=="POST":
        try:
            con=db()
            c=con.cursor()
            c.execute(
                "INSERT INTO users (username,password,is_admin,activo) VALUES (?,?,0,1)",
                (request.form["username"],generate_password_hash(request.form["password"]))
            )
            con.commit()
            con.close()
            return redirect("/admin")
        except:
            error="El usuario ya existe"

    return render_template("crear_usuario.html",error=error)


@app.route("/toggle/<int:user_id>")
@login_required
def toggle_user(user_id):

    if not current_user.is_admin:
        return redirect("/dashboard")

    try:
        con=db()
        c=con.cursor()

        # 🔒 PROTEGER ADMIN (doble seguridad backend)
        c.execute("SELECT is_admin, activo FROM users WHERE id=?", (user_id,))
        r=c.fetchone()

        if r:
            es_admin=r[0]
            activo=r[1]

            if es_admin == 1:
                con.close()
                return redirect("/admin")

            nuevo=0 if activo==1 else 1
            c.execute("UPDATE users SET activo=? WHERE id=?", (nuevo,user_id))

        con.commit()
        con.close()
    except:
        pass

    return redirect("/admin")
# =====================================================
# CAMBIAR CONTRASEÑA (ADMIN)
# =====================================================
@app.route("/cambiar_password/<int:user_id>", methods=["GET","POST"])
@login_required
def cambiar_password(user_id):

    if not current_user.is_admin:
        return redirect("/dashboard")

    con = db()
    c = con.cursor()

    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    user = c.fetchone()

    if not user:
        con.close()
        return redirect("/admin")

    username = user[0]

    if request.method == "POST":
        nueva = request.form["password"]

        c.execute(
            "UPDATE users SET password=? WHERE id=?",
            (generate_password_hash(nueva), user_id)
        )
        con.commit()
        con.close()

        return redirect("/admin")

    con.close()
    return render_template("cambiar_password.html", username=username)

# =====================================================
# EDITAR FICHAJES (ADMIN)
# =====================================================
@app.route("/editar_fichaje", methods=["GET","POST"])
@login_required
def editar_fichaje():

    if not current_user.is_admin:
        return redirect("/dashboard")

    con = db()
    c = con.cursor()

    # lista usuarios
    c.execute("SELECT id, username FROM users")
    users = c.fetchall()

    registros = None

    if request.method == "POST":

        user_id = request.form["user_id"]
        fecha = request.form["fecha"]

        # convertir fecha a formato interno
        fecha_busqueda = fecha[8:10] + "/" + fecha[5:7] + "/" + fecha[0:4]

        c.execute("""
            SELECT id, tipo, fecha
            FROM fichajes
            WHERE user_id=?
            AND fecha LIKE ?
            ORDER BY fecha
        """, (user_id, f"{fecha_busqueda}%"))

        registros = c.fetchall()

    con.close()

    return render_template(
        "editar_fichaje.html",
        users=users,
        registros=registros
    )
@app.route("/guardar_edicion", methods=["POST"])
@login_required
def guardar_edicion():

    if not current_user.is_admin:
        return redirect("/dashboard")

    fichaje_id = request.form["id"]
    nueva_fecha = request.form["fecha"]
    motivo = request.form["motivo"]

    con = db()
    c = con.cursor()

    # obtener datos originales
    c.execute("""
        SELECT fichajes.fecha, users.username
        FROM fichajes
        JOIN users ON users.id = fichajes.user_id
        WHERE fichajes.id=?
    """, (fichaje_id,))
    r = c.fetchone()

    if not r:
        con.close()
        return redirect("/editar_fichaje")

    fecha_original = r[0]
    usuario = r[1]

    # actualizar fichaje
    c.execute(
        "UPDATE fichajes SET fecha=? WHERE id=?",
        (nueva_fecha, fichaje_id)
    )

    # registrar auditoría
    c.execute("""
        INSERT INTO auditoria(
            admin,
            usuario,
            fichaje_id,
            fecha_original,
            fecha_nueva,
            motivo,
            timestamp
        )
        VALUES (?,?,?,?,?,?,?)
    """, (
        current_user.username,
        usuario,
        fichaje_id,
        fecha_original,
        nueva_fecha,
        motivo,
        datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    ))

    con.commit()
    con.close()

    return redirect("/editar_fichaje")


# =====================================================
# FICHAJE
# =====================================================
@app.route("/fichar/<tipo>")
@login_required
def fichar(tipo):

    if tipo not in ("entrada", "salida"):
        abort(400)

    con = db()
    c = con.cursor()
    c.execute(
        "SELECT tipo FROM fichajes WHERE user_id=? ORDER BY fecha DESC LIMIT 1",
        (current_user.id,)
    )
    last = c.fetchone()

    if last is None and tipo == "salida":
        con.close()
        return redirect("/dashboard")

    if last and last[0] == tipo:
        con.close()
        return redirect("/dashboard")

    c.execute(
        "INSERT INTO fichajes (user_id,tipo,fecha) VALUES (?,?,?)",
        (current_user.id, tipo, datetime.now().strftime("%d/%m/%Y %H:%M:%S"))
    )
    con.commit()
    con.close()
    return redirect("/dashboard")


# =====================================================
# FUNCIONES EXPORTACIÓN
# =====================================================
def calcular_detalle(raw):
    resultado = []
    total = 0
    entrada = None

    for username, tipo, fecha in raw:
        momento = datetime.strptime(fecha, "%d/%m/%Y %H:%M:%S")

        if tipo == "entrada":
            entrada = momento

        elif tipo == "salida" and entrada:
            horas = round((momento - entrada).total_seconds()/3600, 2)
            total += horas

            resultado.append([
                momento.strftime("%d/%m/%Y"),
                entrada.strftime("%H:%M"),
                momento.strftime("%H:%M"),
                horas
            ])
            entrada = None

    return resultado, round(total, 2)


def obtener_raw(user_id):
    con = db()
    c = con.cursor()
    c.execute("""
        SELECT users.username, fichajes.tipo, fichajes.fecha
        FROM fichajes
        JOIN users ON users.id = fichajes.user_id
        WHERE fichajes.user_id = ?
        ORDER BY fichajes.fecha
    """, (user_id,))
    rows = c.fetchall()
    con.close()
    return rows


def obtener_nombre_usuario(user_id):
    con = db()
    c = con.cursor()
    c.execute("SELECT username FROM users WHERE id=?", (user_id,))
    r = c.fetchone()
    con.close()
    return r[0] if r else "Desconocido"


# =====================================================
# EXPORTAR USUARIO
# =====================================================
@app.route("/exportar_rango")
@login_required
def exportar_rango():

    tipo = request.args.get("tipo", "pdf")
    raw = obtener_raw(current_user.id)
    rows, total = calcular_detalle(raw)
    nombre = obtener_nombre_usuario(current_user.id)

    headers = ["Fecha","Entrada","Salida","Horas"]

    # ================= CSV =================
    
    if tipo == "csv":
        import os

        # 📁 Carpeta base
        carpeta_csv = os.path.join(os.getcwd(), "informes_csv")
        os.makedirs(carpeta_csv, exist_ok=True)

        # 📁 Carpeta del usuario
        carpeta_usuario = os.path.join(carpeta_csv, nombre)
        os.makedirs(carpeta_usuario, exist_ok=True)

        # 📅 Fecha para nombre archivo
        fecha_archivo = datetime.now().strftime("%Y-%m-%d_%H-%M")

        archivo = os.path.join(
            carpeta_usuario,
            f"registro_{nombre}_{fecha_archivo}.csv"
        )

        with open(archivo, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["BELLEAR ENGLISH"])
            w.writerow(["REGISTRO OFICIAL DE JORNADA"])
            w.writerow([])
            w.writerow([f"Empleado: {nombre}"])
            w.writerow([f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"])
            w.writerow([])
            w.writerow(headers)
            w.writerows(rows)
            w.writerow([])
            w.writerow(["","","TOTAL",f"{total} horas"])

        os.startfile(carpeta_usuario)
        return render_template(
            "mensaje_empresa.html",
            mensaje=f"Informe CSV generado correctamente",
            ruta=archivo
        )
    
  
        

    # ================= PDF =================
    else:
        from reportlab.platypus import Image
        import os

        # 📁 Carpeta destino
        carpeta_pdf = os.path.join(os.getcwd(), "informes_pdf")
        os.makedirs(carpeta_pdf, exist_ok=True)

        # 📝 Nombre archivo
        
        fecha_archivo = datetime.now().strftime("%Y-%m-%d_%H-%M")
        nombre_archivo = f"registro_{nombre}_{fecha_archivo}.pdf"
        
        ruta_pdf = os.path.join(carpeta_pdf, nombre_archivo)
        #from datetime import datetime

        

        # 📄 Crear PDF DIRECTO en archivo
        doc = SimpleDocTemplate(ruta_pdf)
        styles = getSampleStyleSheet()

        elements = []

        # 🖼 LOGO
        logo_path = os.path.join(os.getcwd(), "static", "logo.png")
        if os.path.exists(logo_path):
            elements.append(Image(logo_path, width=120, height=60))
            elements.append(Spacer(1,10))

        # CABECERA
        elements.append(Paragraph("BELLEAR ENGLISH", styles["Title"]))
        elements.append(Paragraph("REGISTRO OFICIAL DE JORNADA LABORAL", styles["Heading2"]))
        elements.append(Spacer(1,10))
        elements.append(Paragraph(f"Empleado: <b>{nombre}</b>", styles["Heading2"]))
        elements.append(Spacer(1,20))

        # TABLA
        data = [headers] + rows + [["","","TOTAL",f"{total} horas"]]
        table = Table(data)
        table.setStyle(TableStyle([
            ("GRID",(0,0),(-1,-1),1,colors.black),
            ("BACKGROUND",(0,0),(-1,0),colors.lightgrey)
        ]))

        elements.append(table)
        
        # ✍️ PIE EMPRESA
        elements.append(Spacer(1,30))
        elements.append(Paragraph("Paseo José Saramago 3 Local 3", styles["Normal"]))
        elements.append(Paragraph("Orkoien - Navarra", styles["Normal"]))
        elements.append(Paragraph("Fdo. Bellkys Moreno", styles["Normal"]))
        
        # 🏁 Construir PDF
        doc.build(elements)

        # 📥 Pantalla información de fichero creado
        
        return render_template(
            "mensaje_empresa.html",
            mensaje=f"Informe PDF generado correctamente",
            ruta_pdf=nombre_archivo
        )
    

# =====================================================
# EXPORTAR ADMIN
# =====================================================
@app.route("/exportar_admin")
@login_required
def exportar_admin():

    if not current_user.is_admin:
        return redirect("/dashboard")

    user_id = int(request.args.get("user_id"))
    tipo = request.args.get("tipo","pdf")

    raw = obtener_raw(user_id)
    rows,total = calcular_detalle(raw)
    nombre = obtener_nombre_usuario(user_id)

    headers=["Fecha","Entrada","Salida","Horas"]

    # ================= CSV =================
    if tipo == "csv":
        import os

        # 📁 Carpeta base
        carpeta_csv = os.path.join(os.getcwd(), "informes_csv")
        os.makedirs(carpeta_csv, exist_ok=True)

        # 📁 Carpeta del usuario
        carpeta_usuario = os.path.join(carpeta_csv, nombre)
        os.makedirs(carpeta_usuario, exist_ok=True)

        # 📅 Fecha para nombre archivo
        fecha_archivo = datetime.now().strftime("%Y-%m-%d_%H-%M")

        archivo = os.path.join(
            carpeta_usuario,
            f"registro_{nombre}_{fecha_archivo}.csv"
        )

        with open(archivo, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["BELLEAR ENGLISH"])
            w.writerow(["REGISTRO OFICIAL DE JORNADA"])
            w.writerow([])
            w.writerow([f"Empleado: {nombre}"])
            w.writerow([f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}"])
            w.writerow([])
            w.writerow(headers)
            w.writerows(rows)
            w.writerow([])
            w.writerow(["","","TOTAL",f"{total} horas"])

        os.startfile(carpeta_usuario)
        return render_template(
            "mensaje_empresa.html",
            mensaje=f"Informe CSV generado correctamente",
            ruta=archivo
        )

    # ================= PDF =================
    else:
        from reportlab.platypus import Image
        import os

        # 📁 Carpeta destino
        carpeta_pdf = os.path.join(os.getcwd(), "informes_pdf")
        os.makedirs(carpeta_pdf, exist_ok=True)

        # 📝 Nombre archivo
        
        fecha_archivo = datetime.now().strftime("%Y-%m-%d_%H-%M")
        nombre_archivo = f"registro_{nombre}_{fecha_archivo}.pdf"
        
        ruta_pdf = os.path.join(carpeta_pdf, nombre_archivo)
        #from datetime import datetime

        

        # 📄 Crear PDF DIRECTO en archivo
        doc = SimpleDocTemplate(ruta_pdf)
        styles = getSampleStyleSheet()

        elements = []

        # 🖼 LOGO
        logo_path = os.path.join(os.getcwd(), "static", "logo.png")
        if os.path.exists(logo_path):
            elements.append(Image(logo_path, width=120, height=60))
            elements.append(Spacer(1,10))

        # CABECERA
        elements.append(Paragraph("BELLEAR ENGLISH", styles["Title"]))
        elements.append(Paragraph("REGISTRO OFICIAL DE JORNADA LABORAL", styles["Heading2"]))
        elements.append(Spacer(1,10))
        elements.append(Paragraph(f"Empleado: <b>{nombre}</b>", styles["Heading2"]))
        elements.append(Spacer(1,20))

        # TABLA
        data = [headers] + rows + [["","","TOTAL",f"{total} horas"]]
        table = Table(data)
        table.setStyle(TableStyle([
            ("GRID",(0,0),(-1,-1),1,colors.black),
            ("BACKGROUND",(0,0),(-1,0),colors.lightgrey)
        ]))

        elements.append(table)
        
        # ✍️ PIE EMPRESA
        elements.append(Spacer(1,30))
        elements.append(Paragraph("Paseo José Saramago 3 Local 3", styles["Normal"]))
        elements.append(Paragraph("Orkoien - Navarra", styles["Normal"]))
        elements.append(Paragraph("Fdo. Bellkys Moreno", styles["Normal"]))
        
        # 🏁 Construir PDF
        doc.build(elements)

        # 📥 Pantalla información de fichero creado
        
        return render_template(
            "mensaje_empresa.html",
            mensaje=f"Informe PDF generado correctamente",
            ruta_pdf=nombre_archivo
        )
    

# =====================================================
# SALIR
# =====================================================
@app.route("/exit")
@login_required
def exit_app():
    logout_user()
    shutdown=request.environ.get("werkzeug.server.shutdown")
    if shutdown:
        shutdown()
    return "Programa cerrado."


# =====================================================
# RUN
# =====================================================
def abrir_navegador():
    webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    threading.Timer(1.2, abrir_navegador).start()
    #app.run()
    app.run(host="0.0.0.0", port=5000, debug=True)


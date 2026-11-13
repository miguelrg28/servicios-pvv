# Manual fácil — Impresoras de la factura

Este manual explica, paso a paso y sin palabras raras, cómo dejar lista una impresora para que la
**factura salga sola al cobrar**. No hace falta saber de computadoras: solo seguir los pasos en
orden.

> Si algo de aquí no te sale igual, **no inventes**: anota en qué paso te quedaste y lo que dice la
> pantalla, y pásaselo a quien lleva el sistema.

---

## 1. Primero: ¿qué caso es el tuyo?

Mira dónde está conectado el cable de la impresora.

| Si la impresora… | Tu caso | Qué tienes que leer |
|---|---|---|
| está conectada **por cable USB a la computadora donde se factura** (lo normal en una caja) | **Caso A** | Solo la parte 2 y la 3. **No instales nada de este repositorio.** |
| está en **otra computadora** o en el **servidor**, y quieres que imprima sin que salga ninguna ventana | **Caso B** | La parte 4 (esa la hace alguien técnico). |

Casi siempre es el **Caso A**.

---

## 2. Caso A — Preparar la computadora de la caja (una sola vez)

### 2.1 Instalar la impresora en Windows

1. Conecta la impresora a la computadora con su cable USB y préndela.
2. Instala el **programa del fabricante** (se llama *controlador* o *driver*).
   - Para la **Star SP500**: en la página de Star Micronics busca "SP500 driver" para Windows.
   - Para otras marcas (Epson, Bixolon…): lo mismo, con su modelo.
3. Abre **Inicio → Configuración → Impresoras y escáneres**. La impresora tiene que aparecer ahí.
4. Haz clic en ella → **Imprimir una página de prueba**. Si sale el papel, vas bien.

### 2.2 Decirle a Windows el tamaño del papel

1. En **Impresoras y escáneres**, haz clic en la impresora → **Preferencias de impresión**.
2. En **Papel** (o *Paper size*) elige el rollo: para la **SP500, el de 76 mm**.
3. Guarda con **Aceptar**.

### 2.3 Que sea la impresora "principal"

Si esa computadora solo imprime facturas:

1. En **Impresoras y escáneres**, apaga la opción **"Permitir que Windows administre la impresora
   predeterminada"**.
2. Haz clic en la impresora → **Establecer como predeterminada**.

---

## 3. Caso A — Configurarla en el panel

Esto lo hace quien tiene permiso de **ajustes de facturación**.

### 3.1 Agregarla

1. Entra al panel y abre **Ajustes** (el engranaje).
2. Baja hasta **Impresión de facturas**.
3. Pulsa el modelo que más se parezca. Para la SP500: **"Star SP500 (matricial, 76 mm)"**.
4. Ponle un nombre fácil, por ejemplo **"Caja 1 — SP500"**.
5. En **"Cómo llega a la impresora"** deja **"Desde el navegador de la caja"**.
6. Pulsa **Guardar**.

### 3.2 Probarla

1. Al lado de la impresora pulsa **"Imprimir prueba"**.
2. Sale el cuadro de imprimir de Chrome. Elige:
   - **Destino:** la impresora de recibos (por ejemplo, la SP500).
   - **Márgenes:** **Ninguno** (está en "Más opciones").
   - **Escala:** **100**.
3. Pulsa **Imprimir**.
4. Mira el final del ticket: hay una fila de números **1234567890…**
   - Si cabe en **un solo renglón**: ✅ está perfecto.
   - Si **se parte en dos**: vuelve a **Editar** y baja **"Letras por renglón"** (de 42 a 40, por
     ejemplo). Guarda y prueba otra vez.
   - Si sobra **mucho espacio a la derecha**: súbelo un poco.

Chrome se acuerda de lo que elegiste, así que esto se hace una vez.

### 3.3 Que no salga el cuadro de imprimir nunca más (opcional, recomendado)

Así la factura sale directo, sin preguntar nada.

1. En el escritorio, haz clic derecho en el ícono de **Google Chrome** → **Copiar**, y luego clic
   derecho en el escritorio → **Pegar acceso directo**.
2. Clic derecho en el acceso directo nuevo → **Propiedades**.
3. En **Destino**, ve al final del texto, deja **un espacio** y escribe:

   ```
   --kiosk-printing
   ```

   Debe quedar más o menos así:
   `"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk-printing`
4. Pulsa **Aceptar**. Cámbiale el nombre a **"Panel — Caja"**.
5. **Cierra todas las ventanas de Chrome** y, desde ahora, abre el panel **siempre con ese
   acceso directo**.

> Para que esto funcione, la impresora de recibos tiene que ser la **predeterminada** de Windows
> (paso 2.3).

### 3.4 Usarla al facturar

1. Factura como siempre y cobra con **F10**.
2. La factura sale sola por la impresora.
3. Debajo de la factura dice **"Imprime en:"**. Ahí puedes elegir otra impresora **solo para esta
   computadora** (las demás cajas no cambian).
4. ¿No salió el papel? (se acabó el rollo, estaba apagada…) Arréglalo y pulsa
   **"Reimprimir FV-…"**. La factura ya está hecha: reimprimir **no** la cobra otra vez.

---

## 4. Caso B — El servicio de impresión (para alguien técnico)

Es un programa pequeño que se queda prendido en una computadora Windows y saca por sus
impresoras lo que le manda el panel, **sin ventanas**. Sirve para:

- imprimir solo a una hora (la hoja del cuadre de las 8 de la mañana), y
- imprimir tickets en una impresora que no está en la caja, con **corte de papel** y **apertura
  de la gaveta** del dinero.

La guía completa, con todos los comandos, está en
**[impresora/INSTALACION.md](impresora/INSTALACION.md)**. En resumen:

1. Instalar Python y bajar este repositorio en `C:\servicios-pvv`.
2. Preparar la carpeta `impresora` (su venv y su archivo `.env` con la **clave**).
3. En el panel, **Ajustes → Servicios de impresión**, agregar esta computadora con la misma
   **clave** y pulsar **"Probar"**. Cada computadora tiene **su propia clave**, y cada empresa ve
   y usa solo las suyas.

   Ahí se elige **quién llama a quién**:
   - **"Ella llama al panel"** (lo normal, y lo que hay que usar en una caja): la computadora sale
     a buscar lo que haya que imprimir. No hace falta ZeroTier ni abrir nada. En su `.env` se
     ponen `PANEL_URL` y el `SERVICIO_ID` que enseña la pantalla.
   - **"El panel la llama"**: hace falta que esa computadora esté en ZeroTier y se pone su
     dirección. Úsalo solo donde ya esté en esa red, como el servidor del taller.
4. Dejarlo prendido solo con el **Programador de tareas**.
5. En el panel, **Ajustes → Impresión de facturas**, elegir **"Por el servicio de impresión"**, la
   **computadora** y el
   **idioma** de la impresora: **Star** para la SP500, **ESC/POS** para casi todas las térmicas.

---

## 5. Si algo sale mal

| Lo que pasa | Lo más probable | Qué hacer |
|---|---|---|
| No sale nada | La impresora está apagada, sin papel o con la tapa abierta | Revísala y pulsa **Reimprimir** |
| Sale en **hoja carta** y no en ticket | No hay ninguna impresora configurada, o la caja tiene elegida otra | Revisa **Ajustes → Impresión de facturas** y el **"Imprime en:"** de la caja |
| El ticket sale **cortado a la derecha** | Demasiadas letras por renglón | Baja **"Letras por renglón"** (parte 3.2) |
| Las letras salen **muy pequeñas** o sobra papel a los lados | Pocas letras por renglón, o márgenes que no son "Ninguno" | Sube las letras por renglón y revisa los márgenes |
| Sale **un metro de papel en blanco** | Windows tiene puesto un papel que no es el rollo | Revisa el tamaño del papel (parte 2.2) |
| Salen **símbolos raros** en vez de letras (Caso B) | El idioma elegido no es el de la impresora | En la SP500, prueba **Star**; en una térmica, **ESC/POS** |
| Sale el cuadro de imprimir cada vez | Chrome no se abrió con el acceso directo especial | Cierra Chrome del todo y ábrelo con **"Panel — Caja"** (parte 3.3) |
| La **SP500 no imprime el código QR** | Es normal: es de agujas y no sabe dibujarlo | El ticket trae el número y el código de seguridad, que sirven para verificar en dgii.gov.do |

---

## Palabras que salen en este manual

- **Controlador (driver):** el programa del fabricante que le enseña a Windows a usar la impresora.
- **Ticket:** el papel angosto que sale de la impresora de recibos.
- **Impresora de recibos:** la impresora pequeña del mostrador que usa un rollo de papel.
- **Predeterminada:** la impresora que Windows usa si nadie elige otra.
- **Gaveta:** el cajón del dinero de la caja.
- **Matricial (de agujas):** impresora que escribe golpeando una cinta, como la SP500. Hace ruido
  y no sabe dibujar códigos QR.
- **Térmica:** impresora que escribe calentando un papel especial. No usa tinta.

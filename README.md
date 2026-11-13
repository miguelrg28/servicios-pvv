# servicios-pvv

Programas chiquitos que corren en las computadoras de cada empresa y conversan con el panel.
Son **generales**: no saben nada de ninguna empresa en concreto, así que cualquier empresa del
panel los puede instalar. Lo que es de un solo negocio (el reloj de asistencia y el lector de
placas de Villa Lubri) sigue en su propio repositorio (`bridge-punch-villalubri`).

> **¿Solo quieres que la factura salga por la impresora de la caja?** Lee el
> **[Manual fácil](MANUAL.md)**: paso a paso, sin palabras técnicas.

| Carpeta | Qué hace | Guía |
|---|---|---|
| [`impresora/`](impresora/) | Saca por las impresoras del equipo lo que manda el panel, sin ventanas: PDF y tickets de factura en crudo (Star, ESC/POS). | [INSTALACION.md](impresora/INSTALACION.md) |

## Reglas para todo lo que se agregue aquí

1. **Cada servicio es una carpeta que se instala sola**: su `requirements.txt`, su `venv\`, su
   `.env.ejemplo`, su `correr.bat` y su `tarea.xml`. Instalar uno no obliga a instalar los demás,
   y si uno se cae los otros siguen.
2. **Nada de una empresa en concreto**: ni nombres, ni IP, ni rutas de un cliente. Eso va en el
   `.env` de cada instalación.
3. **Los secretos, solo en `.env`** (está en `.gitignore`). Sin token, el servicio responde 503:
   una variable olvidada cierra la puerta, no la abre.
4. **Lo que se decide, se decide en el panel.** Estos programas ejecutan; los horarios, las
   impresoras de cada caja y las reglas viven en el panel, donde se ven y se cambian.

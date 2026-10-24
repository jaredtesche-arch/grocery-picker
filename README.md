# Grocery Picker

Fills your Real Canadian Superstore cart in a couple of minutes. You pick the
products on one page, it puts them in your PC Express cart. Checkout, delivery
time and payment stay in the PC Express app.

It uses the store you last ordered from, and it updates itself every time you
open it.

## What you need

- A Windows PC
- Your PC Optimum / PC Express login

## Install (once, about 5 minutes)

1. On this page, click the green **Code** button, then **Download ZIP**.
2. Unzip it somewhere outside OneDrive, like `C:\Users\<you>\Grocery Picker`.
3. Double-click **Setup**. If it installs Python, run Setup a second time after.
4. It asks if you use OurGroceries. Press Enter to skip. You don't need it.
5. A browser opens for the Superstore login. Sign in. The page ends on an
   error or a blank page. That's normal. Copy the whole address from the
   address bar, paste it into the Setup window, press Enter.

## Each shop

1. Double-click **Grocery Picker**. It checks for updates, then opens a page
   in your browser.
2. **Staples**: things you buy every time. Add them once, they show up every shop.
3. **Need anything else?**: search for anything, or tap your most-bought items.
   Use the department buttons to narrow them down.
4. Click a product to pick it, click again to unpick. You can pick more than one.
5. **Build cart**. Then open the PC Express app, pick a delivery time and pay.
6. Close the black window when you're done.

## Optional: OurGroceries

If you'd rather keep your list in [OurGroceries](https://www.ourgroceries.com)
(free app, and the whole family can add to it), the picker reads it and
crosses items off once they're in your cart.

1. Make a free OurGroceries account and a list called **Superstore**.
2. Run **Setup** again and type **y** when it asks about OurGroceries.

Your list items show up at the top of the page, each with a few products to
pick from.

## If something breaks

- An error about a token or login: run **Setup** again.
- It uses Superstore's app connection, which isn't public. If they change it,
  this can stop working until it's patched. Opening the picker picks up the
  fix on its own.

Built on [pcexpress-mcp-server](https://github.com/FireBall1725/pcexpress-mcp-server)
(AGPL-3.0, license in that folder).

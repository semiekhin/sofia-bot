from pyrogram import Client

# Официальные credentials от Telegram Desktop
api_id = 2040
api_hash = "b18441a1ff607e10a989891a5462e627"

app = Client("sofia_pyrogram", api_id=api_id, api_hash=api_hash)

with app:
    me = app.get_me()
    print(f'Успех! {me.first_name}')

from fastapi import FastAPI, HTTPException, Depends, Form
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
import aiosqlite
import os
from dotenv import load_dotenv
from telegram.ext import Application
import secrets

load_dotenv()

app = FastAPI()
security = HTTPBasic()

async def get_bot():
    bot = Application.builder().token(os.getenv('BOT_TOKEN')).build()
    return bot.bot

def verify_auth(credentials: HTTPBasicCredentials = Depends(security)):
    correct_username = os.getenv('ADMIN_USER', 'admin')
    correct_password = os.getenv('ADMIN_PASS', 'admin')
    
    is_correct_username = secrets.compare_digest(credentials.username.encode("utf8"), correct_username.encode("utf8"))
    is_correct_password = secrets.compare_digest(credentials.password.encode("utf8"), correct_password.encode("utf8"))
    
    if not (is_correct_username and is_correct_password):
        raise HTTPException(
            status_code=401,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username

@app.get("/", response_class=HTMLResponse)
async def admin_panel(username: str = Depends(verify_auth)):
    async with aiosqlite.connect('users.db') as db:
        db.row_factory = aiosqlite.Row
        async with db.execute('SELECT * FROM pending_users WHERE status = "pending"') as cursor:
            pending_users = await cursor.fetchall()
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Telegram Bot Admin Panel</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; }
            table { border-collapse: collapse; width: 100%; }
            th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
            th { background-color: #f2f2f2; }
            .approve-btn { background-color: #4CAF50; color: white; padding: 5px 10px; border: none; cursor: pointer; }
            .reject-btn { background-color: #f44336; color: white; padding: 5px 10px; border: none; cursor: pointer; }
        </style>
    </head>
    <body>
        <h1>Pending Verification Requests</h1>
        <table>
            <tr>
                <th>Username</th>
                <th>Invite Code</th>
                <th>Join Date</th>
                <th>Actions</th>
            </tr>
    """
    
    for user in pending_users:
        html_content += f"""
            <tr>
                <td>{user['username']}</td>
                <td>{user['invite_code']}</td>
                <td>{user['join_date']}</td>
                <td>
                    <form style="display: inline" action="/approve/{user['user_id']}" method="post">
                        <button class="approve-btn">Approve</button>
                    </form>
                    <form style="display: inline" action="/reject/{user['user_id']}" method="post">
                        <button class="reject-btn">Reject</button>
                    </form>
                </td>
            </tr>
        """
    
    html_content += """
        </table>
    </body>
    </html>
    """
    
    return html_content

@app.post("/approve/{user_id}")
async def approve_user(user_id: int, username: str = Depends(verify_auth)):
    bot = await get_bot()
    
    async with aiosqlite.connect('users.db') as db:
        # Update user status
        await db.execute(
            'UPDATE pending_users SET status = "approved" WHERE user_id = ?',
            (user_id,)
        )
        await db.commit()
        
        # Get invite link
        invite_link = await bot.create_chat_invite_link(
            chat_id=os.getenv('GROUP_ID'),
            member_limit=1
        )
        
        # Send approval message with invite link
        try:
            await bot.send_message(
                chat_id=user_id,
                text=f"✅ Your verification has been approved! Here's your invite link:\n{invite_link.invite_link}\n\nThis link can only be used once."
            )
        except Exception as e:
            print(f"Failed to send message to user {user_id}: {e}")
    
    return {"status": "success"}

@app.post("/reject/{user_id}")
async def reject_user(user_id: int, username: str = Depends(verify_auth)):
    bot = await get_bot()
    
    async with aiosqlite.connect('users.db') as db:
        await db.execute(
            'UPDATE pending_users SET status = "rejected" WHERE user_id = ?',
            (user_id,)
        )
        await db.commit()
        
        try:
            await bot.send_message(
                chat_id=user_id,
                text="❌ Sorry, your verification request has been rejected."
            )
        except Exception as e:
            print(f"Failed to send message to user {user_id}: {e}")
    
    return {"status": "success"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000) 
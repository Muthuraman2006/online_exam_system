"""
Initialize the database with ONLY the first admin account.
This is required to bootstrap an empty system.

Run: python -m scripts.init_admin

NO demo data, NO mock users, NO seed questions.
System starts EMPTY except for the admin account.

IMPORTANT: The admin email is FIXED as per system requirements.
Admin email: muthuramanm.cse2024@citchennai.net
"""
import asyncio
import sys
import getpass
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import AsyncSessionLocal, init_db
from app.core.security import get_password_hash, verify_password
from app.models.models import User, RoleEnum

# THE ONLY ADMIN EMAIL ALLOWED IN THE SYSTEM
ADMIN_EMAIL = "muthuramanm.cse2024@citchennai.net"


def validate_email(email: str) -> bool:
    """Basic email validation"""
    import re
    pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    return bool(re.match(pattern, email))


def validate_password(password: str) -> tuple[bool, str]:
    """Validate password strength"""
    if len(password) < 8:
        return False, "Password must be at least 8 characters long"
    if not any(c.isupper() for c in password):
        return False, "Password must contain at least one uppercase letter"
    if not any(c.islower() for c in password):
        return False, "Password must contain at least one lowercase letter"
    if not any(c.isdigit() for c in password):
        return False, "Password must contain at least one digit"
    return True, ""


async def check_existing_admin(db: AsyncSession) -> User | None:
    """Check if an admin already exists"""
    result = await db.execute(
        select(User).where(User.role == RoleEnum.ADMIN)
    )
    return result.scalar_one_or_none()


async def create_admin(email: str, password: str, full_name: str) -> User:
    """Create the first admin account"""
    async with AsyncSessionLocal() as db:
        # Check for existing admin
        existing = await check_existing_admin(db)
        if existing:
            print(f"\n⚠️  An admin account already exists: {existing.email}")
            print("Only one admin account can be created through this script.")
            print("Use the admin dashboard to create additional admin accounts.")
            return existing
        
        # Create admin
        admin = User(
            email=email,
            hashed_password=get_password_hash(password),
            full_name=full_name,
            role=RoleEnum.ADMIN,
            is_active=True
        )
        
        db.add(admin)
        await db.commit()
        await db.refresh(admin)
        
        return admin


async def interactive_setup():
    """Interactive admin setup"""
    print("\n" + "=" * 60)
    print("  ONLINE EXAMINATION SYSTEM - INITIAL SETUP")
    print("=" * 60)
    print("\nThis script creates the FIRST admin account.")
    print("The system will start completely EMPTY.")
    print("All data (questions, exams, students) must be created")
    print("manually through the admin dashboard.\n")
    
    # Initialize database
    print("🔧 Initializing database...")
    await init_db()
    print("✅ Database initialized.\n")
    
    # Check for existing admin
    async with AsyncSessionLocal() as db:
        existing = await check_existing_admin(db)
        if existing:
            print(f"⚠️  Admin account already exists: {existing.email}")
            print("\nYou can log in with this account.")
            return
    
    # Get admin details
    print("─" * 40)
    print("Enter details for the admin account:\n")
    
    # Full name
    while True:
        full_name = input("Full Name: ").strip()
        if len(full_name) >= 2:
            break
        print("❌ Name must be at least 2 characters.\n")
    
    # Email
    while True:
        email = input("Email: ").strip().lower()
        if validate_email(email):
            break
        print("❌ Please enter a valid email address.\n")
    
    # Password
    while True:
        print("\nPassword requirements:")
        print("  • At least 8 characters")
        print("  • At least one uppercase letter")
        print("  • At least one lowercase letter")
        print("  • At least one digit\n")
        
        password = getpass.getpass("Password: ")
        valid, msg = validate_password(password)
        if not valid:
            print(f"❌ {msg}\n")
            continue
        
        confirm = getpass.getpass("Confirm Password: ")
        if password != confirm:
            print("❌ Passwords do not match.\n")
            continue
        
        break
    
    # Confirmation
    print("\n" + "─" * 40)
    print("Admin Account Details:")
    print(f"  Name:  {full_name}")
    print(f"  Email: {email}")
    print("─" * 40)
    
    confirm = input("\nCreate this admin account? (yes/no): ").strip().lower()
    if confirm not in ['yes', 'y']:
        print("\n❌ Setup cancelled.")
        return
    
    # Create admin
    print("\n🔧 Creating admin account...")
    admin = await create_admin(email, password, full_name)
    
    print("\n" + "=" * 60)
    print("  ✅ ADMIN ACCOUNT CREATED SUCCESSFULLY")
    print("=" * 60)
    print(f"\n  Email: {admin.email}")
    print(f"  Name:  {admin.full_name}")
    print(f"  Role:  {admin.role.value}")
    print("\n  You can now:")
    print("  1. Start the backend server: uvicorn app.main:app --reload")
    print("  2. Open the frontend: http://localhost:5500/login.html")
    print("  3. Log in with your admin credentials")
    print("  4. Start creating question banks, questions, and exams")
    print("\n" + "=" * 60)


async def quick_setup(email: str, password: str, name: str):
    """Quick non-interactive setup"""
    await init_db()
    
    if not validate_email(email):
        print("❌ Invalid email address")
        sys.exit(1)
    
    valid, msg = validate_password(password)
    if not valid:
        print(f"❌ {msg}")
        sys.exit(1)
    
    admin = await create_admin(email, password, name)
    print(f"✅ Admin account created: {admin.email}")


def main():
    """Entry point"""
    if len(sys.argv) == 4:
        # Quick setup: python -m scripts.init_admin email password "Full Name"
        email, password, name = sys.argv[1], sys.argv[2], sys.argv[3]
        asyncio.run(quick_setup(email, password, name))
    else:
        # Interactive setup
        asyncio.run(interactive_setup())


if __name__ == "__main__":
    main()

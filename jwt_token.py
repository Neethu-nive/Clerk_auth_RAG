# jwt_token.py
import streamlit as st
import jwt
import datetime
import os

# Secret key (make sure it's the same in both files)
SECRET_KEY = os.getenv("JWT_SECRET", "sk_test_DpURagihAWm783nzCdBkFgTNowyraAHjkk3CvupnIB")
ALGORITHM = "HS256"

# Function to generate JWT
def generate_token(user_id: str, expires_in_minutes=60):
    now = datetime.datetime.now(datetime.timezone.utc)  # timezone-aware
    expiration = now + datetime.timedelta(minutes=expires_in_minutes)
    payload = {
        "sub": user_id,
        "exp": expiration,
        "iat": now
    }
    token = jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)
    return token, expiration

# Streamlit UI
st.set_page_config(page_title="JWT Token Generator", layout="centered")
st.title("🔐 JWT Token Generator for FastAPI")

user_id = st.text_input("Enter User ID", value="user_123")
expiry = st.number_input("Token Expiration (minutes)", min_value=1, value=60)

if st.button("Generate JWT Token"):
    token, exp = generate_token(user_id, expires_in_minutes=expiry)
    st.success("✅ JWT Token Generated Successfully!")
    st.subheader("Your JWT Token:")
    st.code(token, language="text")

    st.markdown(f"**Token Expires At:** `{exp.strftime('%Y-%m-%d %H:%M:%S %Z')}`")
    test_url = f"http://localhost:8000/protected"
    st.markdown(f"📡 Test with curl:")
    st.code(f'curl -H "Authorization: Bearer {token}" {test_url}', language="bash")

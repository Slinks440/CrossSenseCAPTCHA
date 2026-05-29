import os
import jwt
from functools import wraps
from flask import Flask, request, jsonify

app = Flask(__name__)
# Ensure this secret is the exact same one used in app.py
app.config["JWT_SECRET"] = os.environ.get("JWT_SECRET", "dummy_secret_for_demo")

def verify_captcha_token(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Read CaptchaToken from HttpOnly Cookie
        token = request.cookies.get("CaptchaToken")
        if not token:
            return jsonify({"error": "Captcha required"}), 403
            
        # 2. Read client_sign_nonce from POST Body
        data = request.get_json(silent=True) or {}
        client_nonce = data.get("client_sign_nonce")
        
        try:
            # 3. Validate JWT signature and expiration
            payload = jwt.decode(token, app.config["JWT_SECRET"], algorithms=["HS256"])
            
            # 4. Compare the client_sign_nonce with the sign_seed
            # In a production app, the Wasm module hashes the sign_seed via HKDF.
            # For this interceptor demo, we assume the frontend simply returns it or its hash.
            if not client_nonce or client_nonce != payload.get("sign_seed"):
                raise ValueError("Nonce mismatch")
                
        except Exception as e:
            # 5. Clearance Protocol: Burn the cookie on failure
            resp = jsonify({"error": "Invalid or expired captcha"})
            resp.set_cookie("CaptchaToken", "", max_age=0) 
            return resp, 403
            
        # 5. Cleansweep Protocol: Burn the cookie on success
        resp = f(*args, **kwargs)
        
        # Ensure we return a Flask Response object to set cookies
        if not isinstance(resp, app.response_class):
            if isinstance(resp, tuple):
                resp = app.make_response(resp)
            else:
                resp = app.make_response(resp)
                
        resp.set_cookie("CaptchaToken", "", max_age=0)
        return resp
        
    return decorated_function

@app.route("/api/login", methods=["POST"])
@verify_captcha_token
def login():
    """
    Dummy business route protected by the V8 Captcha Interceptor.
    If reached, the CAPTCHA is fully verified and consumed.
    """
    return jsonify({"success": True, "msg": "Login successful. Captcha token burned."})

if __name__ == "__main__":
    app.run(port=5001)

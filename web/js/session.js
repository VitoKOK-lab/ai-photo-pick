// session.js - session_id 管理
const SESSION_KEY = "jewelry_db_session_id";

export function getSessionId() {
    let sid = localStorage.getItem(SESSION_KEY);
    if (!sid) {
        sid = "sess_" + Math.random().toString(36).substring(2, 12) + "_" + Date.now();
        localStorage.setItem(SESSION_KEY, sid);
    }
    return sid;
}

export function resetSession() {
    localStorage.removeItem(SESSION_KEY);
}

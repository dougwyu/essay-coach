// Session ID management
function getSessionId() {
    let sid = localStorage.getItem('essay_coach_session_id');
    if (!sid) {
        sid = crypto.randomUUID();
        localStorage.setItem('essay_coach_session_id', sid);
    }
    return sid;
}

// ============================================================
// STUDENT
// ============================================================

// Module-level resolved session ID for this page load
let _resolvedSessionId = null;

async function initStudent() {
    // Try to get a server-managed session_id for logged-in students
    const res = await fetch(`/api/student/session/${QUESTION_ID}`);
    if (res.ok) {
        const data = await res.json();
        _resolvedSessionId = data.session_id;
        // Show identity indicator
        const meRes = await fetch('/api/student/auth/me');
        if (meRes.ok) {
            const student = await meRes.json();
            const identityEl = document.getElementById('student-identity');
            if (identityEl) {
                identityEl.innerHTML =
                    `Already signed in as <strong>${escapeHtml(student.username)}</strong> &nbsp;·&nbsp; ` +
                    `<a href="#" onclick="studentSignOut(); return false;">Sign out</a>`;
            }
        }
    } else {
        // Anonymous fallback
        _resolvedSessionId = getSessionId();
    }
    loadAttemptHistory();
}

async function submitForFeedback() {
    const answer = document.getElementById('student-answer').value.trim();
    if (!answer) {
        alert('Please write an answer before submitting.');
        return;
    }

    const btn = document.getElementById('submit-btn');
    btn.disabled = true;
    btn.textContent = 'Waiting for feedback...';

    const feedbackSection = document.getElementById('feedback-section');
    const feedbackContent = document.getElementById('feedback-content');
    const indicator = document.getElementById('streaming-indicator');

    feedbackContent.innerHTML = '';
    feedbackSection.style.display = 'none';
    const scoreSection = document.getElementById('score-section');
    const scoreContent = document.getElementById('score-content');
    if (scoreSection) { scoreSection.style.display = 'none'; scoreContent.innerHTML = ''; }
    indicator.style.display = 'flex';

    try {
        const response = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question_id: QUESTION_ID,
                student_answer: answer,
                session_id: _resolvedSessionId
            })
        });

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullFeedback = '';

        indicator.style.display = 'none';
        feedbackSection.style.display = 'block';

        while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            const chunk = decoder.decode(value, { stream: true });
            const lines = chunk.split('\n');

            for (const line of lines) {
                if (line.startsWith('data: ')) {
                    try {
                        const data = JSON.parse(line.slice(6));
                        if (data.text) {
                            fullFeedback += data.text;
                            feedbackContent.innerHTML = formatFeedback(fullFeedback);
                        }
                        if (data.done) {
                            document.getElementById('attempt-counter').textContent =
                                `Attempt ${data.attempt_number}`;
                            loadAttemptHistory();
                        }
                        if (data.score) {
                            renderScore(data.score);
                        }
                    } catch (e) {
                        // Skip malformed JSON
                    }
                }
            }
        }
    } catch (err) {
        indicator.style.display = 'none';
        feedbackSection.style.display = 'block';
        feedbackContent.innerHTML = '<p class="error">Failed to get feedback. Please try again.</p>';
    }

    btn.disabled = false;
    btn.textContent = 'Submit for Feedback';
}

function formatFeedback(text) {
    // Convert markdown-like headers and bold
    let html = text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^### (.*$)/gm, '<h4>$1</h4>')
        .replace(/^## (.*$)/gm, '<h3>$1</h3>')
        .replace(/^- (.*$)/gm, '<li>$1</li>')
        .replace(/\n\n/g, '</p><p>')
        .replace(/\n/g, '<br>');

    // Wrap loose <li> in <ul>
    html = html.replace(/((?:<li>.*<\/li>(?:<br>)?)+)/g, '<ul>$1</ul>');
    return '<p>' + html + '</p>';
}

async function loadAttemptHistory() {
    if (typeof QUESTION_ID === 'undefined') return;

    const res = await fetch(`/api/attempts/${QUESTION_ID}?session_id=${_resolvedSessionId}`);
    const data = await res.json();
    const container = document.getElementById('history-content');
    if (!container) return;

    if (data.attempts.length === 0) {
        container.innerHTML = '<p class="empty-state">No previous attempts yet.</p>';
        return;
    }

    container.innerHTML = data.attempts.map((a, i) => `
        <div class="history-item">
            <div class="history-item-header" onclick="this.parentElement.classList.toggle('expanded')">
                <strong>Attempt ${a.attempt_number}</strong>
                <span class="history-date">${new Date(a.created_at).toLocaleString()}</span>
            </div>
            <div class="history-item-body">
                <div class="history-answer">
                    <h4>Your Answer</h4>
                    <p>${escapeHtml(a.student_answer)}</p>
                </div>
                <div class="history-feedback">
                    <h4>Feedback</h4>
                    <div>${formatFeedback(a.feedback || '')}</div>
                </div>
                <div class="score-section" style="display:none"><div class="score-content"></div></div>
            </div>
        </div>
    `).join('');

    data.attempts.forEach((a, i) => {
        if (a.score_data) {
            const card = container.querySelectorAll('.history-item')[i];
            renderScore(a.score_data, card);
        }
    });

    // Update attempt counter
    const counter = document.getElementById('attempt-counter');
    if (counter) {
        counter.textContent = `${data.attempts.length} previous attempt${data.attempts.length !== 1 ? 's' : ''}`;
    }
}

function toggleHistory() {
    const content = document.getElementById('history-content');
    const text = document.getElementById('history-toggle-text');
    if (content.style.display === 'none') {
        content.style.display = 'block';
        text.textContent = 'Hide Revision History';
    } else {
        content.style.display = 'none';
        text.textContent = 'Show Revision History';
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function renderScore(scoreData, container = null) {
    const section = container
        ? container.querySelector('.score-section')
        : document.getElementById('score-section');
    const content = container
        ? container.querySelector('.score-content')
        : document.getElementById('score-content');
    if (!section || !content) return;
    const rows = scoreData.breakdown.map(item =>
        `<tr>
           <td class="score-label">${escapeHtml(item.label)}</td>
           <td class="score-fraction">${item.awarded} / ${item.max}</td>
         </tr>`
    ).join('');
    content.innerHTML =
        `<div class="score-total">Score: ${scoreData.total_awarded} / ${scoreData.total_max}</div>` +
        `<table class="score-breakdown">${rows}</table>`;
    section.style.display = 'block';
}

// ============================================================
// INSTRUCTOR
// ============================================================

// ---- Auth helpers ----

function handleAuthError(res) {
    if (res.status === 401) {
        window.location.href = '/login';
        return true;
    }
    return false;
}

// ---- Invite code ----

async function loadInviteCode() {
    const res = await fetch('/api/settings/invite-code');
    if (handleAuthError(res)) return;
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('invite-code-display').textContent = data.invite_code;
}

async function rotateInviteCode() {
    if (!confirm('Rotate the invite code? The current code will stop working immediately.')) return;
    const res = await fetch('/api/settings/invite-code', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
    });
    if (handleAuthError(res)) return;
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById('invite-code-display').textContent = data.invite_code;
}

let currentQuestions = {};

function initInstructor() {
    document.getElementById('question-form').addEventListener('submit', handleQuestionSubmit);
}

function applyClassFilter() {
    const filterVal = document.getElementById('class-filter').value;
    document.querySelectorAll('.question-card').forEach(card => {
        if (!filterVal || card.dataset.classId === filterVal) {
            card.style.display = '';
        } else {
            card.style.display = 'none';
        }
    });
}

async function handleQuestionSubmit(e) {
    e.preventDefault();

    const editId = document.getElementById('edit-id').value;
    const payload = {
        title: document.getElementById('q-title').value,
        prompt: document.getElementById('q-prompt').value,
        model_answer: document.getElementById('q-model-answer').value,
        rubric: document.getElementById('q-rubric').value,
        class_id: document.getElementById('q-class').value,
    };

    let res;
    if (editId) {
        res = await fetch(`/api/questions/${editId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } else {
        res = await fetch('/api/questions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    }
    if (handleAuthError(res)) return;
    window.location.reload();
}

async function editQuestion(id) {
    const dataRes = await fetch(`/api/questions/detail/${id}`);
    if (handleAuthError(dataRes)) return;
    if (!dataRes.ok) return;
    const q = await dataRes.json();
    document.getElementById('edit-id').value = id;
    document.getElementById('q-title').value = q.title;
    document.getElementById('q-prompt').value = q.prompt;
    document.getElementById('q-model-answer').value = q.model_answer;
    document.getElementById('q-rubric').value = q.rubric || '';
    document.getElementById('q-class').value = q.class_id || '';
    document.getElementById('form-title').textContent = 'Edit Question';
    document.getElementById('submit-btn').textContent = 'Update Question';
    document.getElementById('cancel-btn').style.display = 'inline-block';
    window.scrollTo({ top: 0, behavior: 'smooth' });
}

function cancelEdit() {
    document.getElementById('edit-id').value = '';
    document.getElementById('question-form').reset();
    document.getElementById('form-title').textContent = 'Create New Question';
    document.getElementById('submit-btn').textContent = 'Create Question';
    document.getElementById('cancel-btn').style.display = 'none';
}

async function deleteQuestion(id) {
    if (!confirm('Delete this question? This cannot be undone.')) return;
    const res = await fetch(`/api/questions/${id}`, { method: 'DELETE' });
    if (handleAuthError(res)) return;
    window.location.reload();
}

// ---- Classes (instructor-classes.html) ----

function initClasses() {
    // no setup needed currently
}

async function createClass() {
    const name = document.getElementById('new-class-name').value.trim();
    if (!name) { alert('Enter a class name.'); return; }
    const res = await fetch('/api/classes', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name }),
    });
    if (handleAuthError(res)) return;
    if (!res.ok) return;
    window.location.reload();
}

async function joinClass() {
    const code = document.getElementById('join-instructor-code').value.trim().toUpperCase();
    if (!code) { alert('Enter an instructor code.'); return; }
    const res = await fetch('/api/classes/join', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ instructor_code: code }),
    });
    if (handleAuthError(res)) return;
    if (res.status === 400) { alert('You are already a member of this class.'); return; }
    if (res.status === 404) { alert('Class not found. Check the code.'); return; }
    if (!res.ok) return;
    window.location.reload();
}

async function rotateStudentCode(classId) {
    if (!confirm('Rotate the student code? Students using the old code will need the new one.')) return;
    const res = await fetch(`/api/classes/${classId}/student-code`, { method: 'PUT' });
    if (handleAuthError(res)) return;
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById(`student-code-${classId}`).textContent = data.student_code;
}

async function rotateInstructorCode(classId) {
    if (!confirm('Rotate the instructor invite code? The old code will stop working.')) return;
    const res = await fetch(`/api/classes/${classId}/instructor-code`, { method: 'PUT' });
    if (handleAuthError(res)) return;
    if (!res.ok) return;
    const data = await res.json();
    document.getElementById(`instructor-code-${classId}`).textContent = data.instructor_code;
}

// ---- Student class helpers ----

async function initStudentLanding() {
    const params = new URLSearchParams(window.location.search);
    if (params.get('clear')) {
        localStorage.removeItem('essay_coach_class_id');
    }

    // Check if already authenticated
    const res = await fetch('/api/student/auth/me');
    if (res.ok) {
        const student = await res.json();
        const stored = localStorage.getItem('essay_coach_class_id');
        if (stored) {
            window.location.href = `/student/${stored}`;
            return;
        }
        showClassCodePanel(true, student.username);
    } else {
        // Not logged in — check for stored class_id (anonymous fast-path)
        const stored = localStorage.getItem('essay_coach_class_id');
        if (stored) {
            window.location.href = `/student/${stored}`;
            return;
        }
        // Show auth panel (Step 1)
        document.getElementById('auth-panel').style.display = 'block';
        document.getElementById('class-code-panel').style.display = 'none';
    }
}

function showClassCodePanel(loggedIn, username) {
    document.getElementById('auth-panel').style.display = 'none';
    document.getElementById('class-code-panel').style.display = 'block';
    const identityEl = document.getElementById('student-identity');
    if (loggedIn && username) {
        identityEl.innerHTML =
            `Already signed in as <strong>${escapeHtml(username)}</strong> &nbsp;·&nbsp; ` +
            `<a href="#" onclick="studentSignOut(); return false;">Sign out</a>`;
    } else {
        identityEl.innerHTML =
            `Browsing anonymously &nbsp;·&nbsp; ` +
            `<a href="#" onclick="showAuthPanel(); return false;">Sign in</a>`;
    }
}

function showAuthPanel() {
    document.getElementById('auth-panel').style.display = 'block';
    document.getElementById('class-code-panel').style.display = 'none';
}

async function studentSignIn() {
    const username = document.getElementById('auth-username').value.trim();
    const password = document.getElementById('auth-password').value;
    const errorEl = document.getElementById('auth-error');
    errorEl.style.display = 'none';
    // Hide the email field (used only for registration)
    document.getElementById('auth-email-field').style.display = 'none';
    const res = await fetch('/api/student/auth/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username_or_email: username, password })
    });
    if (!res.ok) {
        errorEl.textContent = 'Invalid username or password.';
        errorEl.style.display = 'block';
        return;
    }
    const data = await res.json();
    showClassCodePanel(true, data.username);
}

async function studentRegister() {
    const errorEl = document.getElementById('auth-error');
    errorEl.style.display = 'none';
    // Show the email field if not already visible
    const emailField = document.getElementById('auth-email-field');
    if (emailField.style.display === 'none') {
        // First click: reveal email field and prompt user to fill it in
        emailField.style.display = 'block';
        document.getElementById('auth-email').focus();
        errorEl.textContent = 'Enter your email above, then click Create account again.';
        errorEl.style.display = 'block';
        return;
    }
    const username = document.getElementById('auth-username').value.trim();
    const email = document.getElementById('auth-email').value.trim();
    const password = document.getElementById('auth-password').value;
    const res = await fetch('/api/student/auth/register', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ username, email, password })
    });
    if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        errorEl.textContent = data.detail || 'Registration failed. Check your details and try again.';
        errorEl.style.display = 'block';
        return;
    }
    const data = await res.json();
    showClassCodePanel(true, data.username);
}

async function studentSignOut() {
    await fetch('/api/student/auth/logout', { method: 'POST' });
    window.location.href = '/student';
}

async function resolveClassCode() {
    const code = document.getElementById('class-code-input').value.trim().toUpperCase();
    if (!code) return;
    const errorEl = document.getElementById('class-code-error');
    errorEl.style.display = 'none';
    const btn = document.querySelector('.class-entry-form .btn-primary');
    if (btn) btn.disabled = true;
    const res = await fetch(`/api/classes/by-student-code/${code}`);
    if (!res.ok) {
        errorEl.style.display = 'block';
        if (btn) btn.disabled = false;
        return;
    }
    const data = await res.json();
    localStorage.setItem('essay_coach_class_id', data.class_id);
    window.location.href = `/student/${data.class_id}`;
}

function clearClass() {
    localStorage.removeItem('essay_coach_class_id');
    window.location.href = '/student';
}

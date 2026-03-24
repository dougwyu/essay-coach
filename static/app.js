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

function initStudent() {
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
    indicator.style.display = 'flex';

    try {
        const response = await fetch('/api/feedback', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                question_id: QUESTION_ID,
                student_answer: answer,
                session_id: getSessionId()
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

    const res = await fetch(`/api/attempts/${QUESTION_ID}?session_id=${getSessionId()}`);
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
            </div>
        </div>
    `).join('');

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

// ============================================================
// INSTRUCTOR
// ============================================================

let currentQuestions = {};

function initInstructor() {
    document.getElementById('question-form').addEventListener('submit', handleQuestionSubmit);
}

async function handleQuestionSubmit(e) {
    e.preventDefault();

    const editId = document.getElementById('edit-id').value;
    const payload = {
        title: document.getElementById('q-title').value,
        prompt: document.getElementById('q-prompt').value,
        model_answer: document.getElementById('q-model-answer').value,
        rubric: document.getElementById('q-rubric').value
    };

    if (editId) {
        await fetch(`/api/questions/${editId}`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    } else {
        await fetch('/api/questions', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
    }

    window.location.reload();
}

async function editQuestion(id) {
    const res = await fetch(`/api/questions/${id}`, { method: 'GET' });
    // The instructor page has the data in the HTML, so we fetch via the API
    // For simplicity, reload with a fetch to the instructor-specific endpoint
    // Actually, we'll use a dedicated instructor API endpoint
    // For now, use the page data approach

    // Fetch question data (instructor has access to full data)
    const response = await fetch(`/instructor`);
    const html = await response.text();

    // Simpler: just scroll to form and let user re-enter
    // Better approach: add an instructor-only API endpoint
    // For MVP, use the card data attributes

    const card = document.querySelector(`.question-card[data-id="${id}"]`);
    if (!card) return;

    // We need the full data. Let's add a simple fetch.
    const dataRes = await fetch(`/api/questions/detail/${id}`);
    if (dataRes.ok) {
        const q = await dataRes.json();
        document.getElementById('edit-id').value = id;
        document.getElementById('q-title').value = q.title;
        document.getElementById('q-prompt').value = q.prompt;
        document.getElementById('q-model-answer').value = q.model_answer;
        document.getElementById('q-rubric').value = q.rubric || '';
        document.getElementById('form-title').textContent = 'Edit Question';
        document.getElementById('submit-btn').textContent = 'Update Question';
        document.getElementById('cancel-btn').style.display = 'inline-block';
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }
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
    await fetch(`/api/questions/${id}`, { method: 'DELETE' });
    window.location.reload();
}

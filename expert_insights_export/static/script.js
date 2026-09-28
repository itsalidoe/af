let currentQuery = '';
let currentPage = 1;
let totalPages = 1;
let sortBy = 'released_at';
let sortOrder = 'desc';

function searchInterviews() {
    const query = document.getElementById('searchInput').value;
    if (query === currentQuery) return;
    currentQuery = query;
    currentPage = 1;
    fetchInterviews(query);
}

function fetchInterviews(query = '') {
    const resultsContainer = document.getElementById('searchResults');
    resultsContainer.innerHTML = '<p class="loading">Loading...</p>';

    const url = query
        ? `/api/search?query=${encodeURIComponent(query)}&page=${currentPage}&sort_by=${sortBy}&sort_order=${sortOrder}`
        : `/api/interviews?page=${currentPage}&sort_by=${sortBy}&sort_order=${sortOrder}`;

    fetch(url)
        .then(r => r.json())
        .then(data => {
            displayResults(data.interviews);
            updatePagination(data.total, data.per_page);
        })
        .catch(err => {
            console.error('Error:', err);
            resultsContainer.innerHTML = '<p class="error">An error occurred. Please try again.</p>';
        });
}

function displayResults(results) {
    const container = document.getElementById('searchResults');
    container.innerHTML = '';

    if (!results || results.length === 0) {
        container.innerHTML = '<p class="no-results">No results found.</p>';
        return;
    }

    results.forEach(r => {
        const item = document.createElement('div');
        item.className = 'result-item';

        const company = r.primary_companies || 'Unknown';
        const ticker = r.primary_company_ticker ? ` (${r.primary_company_ticker})` : '';
        const descriptor = r.source_descriptor ? `<span class="topic">${r.source_descriptor}</span>` : '';
        const date = r.released_at ? new Date(r.released_at).toLocaleDateString() : '';
        const snippet = r.snippet ? `<p class="snippet">${r.snippet}</p>` : '';

        item.innerHTML = `
            <h3>${r.title || '(No title)'}</h3>
            <p class="company">${company}${ticker}</p>
            <p class="date">${date}</p>
            <div class="topics">${descriptor}</div>
            <p class="summary">${truncate(r.summary || '', 150)}</p>
            ${snippet}
        `;
        item.onclick = () => displayPDF(r.id);
        container.appendChild(item);
    });
}

function truncate(text, max) {
    return text.length <= max ? text : text.substr(0, max) + '...';
}

function displayPDF(docId) {
    const iframe = document.getElementById('pdfContainer');
    const placeholder = document.getElementById('pdfPlaceholder');
    iframe.src = `/pdf/${docId}`;
    iframe.style.display = 'block';
    placeholder.style.display = 'none';
}

function updatePagination(total, perPage) {
    totalPages = Math.ceil(total / perPage);
    document.getElementById('pageInfo').textContent = `Page ${currentPage} of ${totalPages} (${total.toLocaleString()} docs)`;
    document.getElementById('prevPage').disabled = currentPage === 1;
    document.getElementById('nextPage').disabled = currentPage === totalPages;
}

function changePage(delta) {
    currentPage += delta;
    fetchInterviews(currentQuery);
}

function updateSort() {
    sortBy = document.getElementById('sortBy').value;
    currentPage = 1;
    fetchInterviews(currentQuery);
}

function toggleSortOrder() {
    sortOrder = sortOrder === 'asc' ? 'desc' : 'asc';
    document.getElementById('sortOrder').innerHTML = sortOrder === 'asc' ? '&#8593;' : '&#8595;';
    currentPage = 1;
    fetchInterviews(currentQuery);
}

function debounce(func, wait) {
    let timeout;
    return function (...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), wait);
    };
}

document.getElementById('searchInput').addEventListener('input', debounce(searchInterviews, 300));

function loadStatus() {
    fetch('/api/status')
        .then(r => r.json())
        .then(s => {
            const el = document.getElementById('indexStatus');
            el.textContent = s.indexed === null
                ? 'Searching titles, companies, expert types and summaries. Run index_transcripts.py to search inside the transcripts too.'
                : `Searching titles, companies, expert types, summaries and the text of ${s.indexed.toLocaleString()} transcripts.`;
        })
        .catch(() => {});
}

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('searchInput').focus();
    loadStatus();
    fetchInterviews();
});

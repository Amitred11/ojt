/**
 * OJT Log System - Frontend Logic
 */

// Initialize Lucide Icons
lucide.createIcons();

// 1. DATA BRIDGE
// We assume OJT_CONFIG is defined in the HTML before this script loads
const HOLIDAYS = window.OJT_CONFIG?.holidays || [];
const TODAY_STR = window.OJT_CONFIG?.today || '';

// 2. FORM AJAX HANDLER (Logging Hub)
const logForm = document.getElementById('log-form');
if (logForm) {
    logForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = document.getElementById('submit-btn');
        btn.innerText = "Processing...";
        btn.disabled = true;

        const formData = new FormData(e.target);
        try {
            await fetch(window.location.href, { method: 'POST', body: formData });
            
            // Silently refresh UI components
            const response = await fetch(window.location.href);
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            ['stats-container', 'intelligence-container', 'eta-container', 'archive-container'].forEach(id => {
                const el = document.getElementById(id);
                const newEl = doc.getElementById(id);
                if (el && newEl) el.innerHTML = newEl.innerHTML;
            });

            resetForm();
            lucide.createIcons();
            btn.disabled = false;
        } catch (err) {
            console.error("Submission failed", err);
            btn.innerText = "Error - Retry";
            btn.disabled = false;
        }
    });
}

// 3. CONFIG UPDATES HANDLER
const configForm = document.getElementById('config-form');
if (configForm) {
    configForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        const btn = e.target.querySelector('button[type="submit"]');
        const originalText = btn.innerText;
        btn.innerText = "Recalculating History...";
        
        const formData = new FormData(e.target);
        try {
            await fetch(window.location.href, { 
                method: 'POST', 
                body: formData,
                headers: {'X-Requested-With': 'XMLHttpRequest'} 
            });
            
            const response = await fetch(window.location.href);
            const html = await response.text();
            const parser = new DOMParser();
            const doc = parser.parseFromString(html, 'text/html');

            ['stats-container', 'intelligence-container', 'eta-container', 'archive-container'].forEach(id => {
                const el = document.getElementById(id);
                const newEl = doc.getElementById(id);
                if(el && newEl) el.innerHTML = newEl.innerHTML;
            });

            btn.innerText = "History Synced!";
            setTimeout(() => { btn.innerText = originalText; }, 2000);
            lucide.createIcons();
        } catch (err) {
            btn.innerText = "Error Syncing";
            console.error(err);
        }
    });
}

// --- CORE FUNCTIONS ---

window.setLogMode = function(mode) {
    const liveSec = document.getElementById('section-live');
    const manualSec = document.getElementById('section-manual');
    const liveBtn = document.getElementById('mode-live-btn');
    const manualBtn = document.getElementById('mode-manual-btn');

    if (mode === 'live') {
        liveSec?.classList.remove('hidden');
        manualSec?.classList.add('hidden');
        if(liveBtn) liveBtn.className = "px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all bg-indigo-500 text-white shadow-lg";
        if(manualBtn) manualBtn.className = "px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all text-slate-500 hover:text-white";
    } else {
        liveSec?.classList.add('hidden');
        manualSec?.classList.remove('hidden');
        if(manualBtn) manualBtn.className = "px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all bg-indigo-500 text-white shadow-lg";
        if(liveBtn) liveBtn.className = "px-6 py-2 rounded-xl text-[10px] font-black uppercase tracking-widest transition-all text-slate-500 hover:text-white";
    }
};

window.handleDateChange = function() {
    const logIdInput = document.getElementById('log_id');
    const manualInput = document.getElementById('manual_credit');
    const title = document.getElementById('form-title');
    const submitBtn = document.getElementById('submit-btn');
    const cancelBtn = document.getElementById('cancel-edit');
    
    // If log_id has a value, we are currently in EDIT mode. 
    // Changing the date should FORCE a reset to "New Entry" mode.
    if (logIdInput && logIdInput.value !== "") {
        logIdInput.value = ""; // Clear the ID
        if (manualInput) manualInput.value = "";
        if (title) title.innerText = "New Entry";
        if (submitBtn) submitBtn.innerText = "Log Session";
        if (cancelBtn) cancelBtn.classList.add('hidden');
        
        // Optional: Clear times so you don't accidentally log previous day's times
        document.getElementById('am_in').value = "";
        document.getElementById('am_out').value = "";
        document.getElementById('pm_in').value = "";
        document.getElementById('pm_out').value = "";
    }

    // Now run the restriction check for the fresh "New Entry"
    checkDateRestrictions();
};

window.checkDateRestrictions = function(forceUnblock = false) {
    const dateInput = document.getElementById('log_date');
    const logIdInput = document.getElementById('log_id');
    const overlay = document.getElementById('restriction-overlay');
    const submitBtn = document.getElementById('submit-btn');
    const punchBtn = document.getElementById('punch-btn');
    
    // 1. EDIT MODE BYPASS
    // Only bypass if we currently have an ID (meaning we haven't switched to New Entry)
    const isEditing = forceUnblock === true || (logIdInput && logIdInput.value.trim() !== "");

    if (isEditing) {
        if (overlay) {
            overlay.classList.add('hidden');
            overlay.classList.remove('flex');
        }
        if (submitBtn) submitBtn.disabled = false;
        return; 
    }

    const dateStr = dateInput?.value;
    if (!dateStr) return;

    // 2. LOGIC ENGINE (March 20+ Friday Block)
    const getBlockStatus = (targetDateStr) => {
        const parts = targetDateStr.split('-');
        const y = parseInt(parts[0], 10);
        const m = parseInt(parts[1], 10);
        const d = parseInt(parts[2], 10);
        
        const dateObj = new Date(y, m - 1, d, 12, 0, 0);
        const dayOfWeek = dateObj.getDay(); 
        
        const targetNumeric = (y * 10000) + (m * 100) + d;
        const transitionNumeric = 20260320; // Block begins Friday, March 20

        const is10hMode = document.getElementById('cfg-10h')?.checked;
        const weekendAllowed = document.querySelector('input[name="allow_weekend_duty"]')?.checked;
        const holidayAllowed = document.querySelector('input[name="allow_holiday_duty"]')?.checked;

        const isWeekend = (dayOfWeek === 0 || dayOfWeek === 6);
        const isFriday = (dayOfWeek === 5);
        const isHoliday = (window.OJT_CONFIG?.holidays || []).includes(targetDateStr);

        let blocked = false;
        let type = "";

        if (isWeekend && !weekendAllowed) {
            blocked = true;
            type = "Weekend";
        } else if (isHoliday && !holidayAllowed) {
            blocked = true;
            type = "Holiday";
        } else if (is10hMode && isFriday && targetNumeric >= transitionNumeric) {
            blocked = true;
            type = "Friday (Compressed)";
        }

        return { blocked, type };
    };

    const status = getBlockStatus(dateStr);

    // 3. APPLY UI CHANGES
    if (status.blocked) {
        overlay?.classList.remove('hidden'); 
        overlay?.classList.add('flex');
        const msgEl = document.getElementById('restriction-msg');
        if(msgEl) msgEl.innerText = `${status.type} Logging Blocked`;
        if(submitBtn) submitBtn.disabled = true;
    } else {
        overlay?.classList.add('hidden'); 
        overlay?.classList.remove('flex');
        if(submitBtn) submitBtn.disabled = false;
    }
};

window.editLog = function(id, date, amIn, amOut, pmIn, pmOut, manualCredit) {
    setLogMode('manual');

    const safeSet = (id, val) => {
        const el = document.getElementById(id);
        if (el) el.value = val || "";
    };

    // 1. Set the values
    safeSet('log_id', id);
    safeSet('log_date', date);
    safeSet('am_in', amIn);
    safeSet('am_out', amOut);
    safeSet('pm_in', pmIn);
    safeSet('pm_out', pmOut);
    safeSet('manual_credit', manualCredit);
    
    // 2. Update UI
    const title = document.getElementById('form-title');
    if (title) title.innerText = "Update Session";
    
    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) submitBtn.innerText = "Update Session";

    const cancelBtn = document.getElementById('cancel-edit');
    if (cancelBtn) cancelBtn.classList.remove('hidden');

    // 3. Force Unblock: Since log_id is now set, this will hide the overlay
    checkDateRestrictions();

    window.scrollTo({ top: 0, behavior: 'smooth' });
};

window.resetForm = function() {
    const form = document.getElementById('log-form');
    if(form) form.reset();
    
    const idInput = document.getElementById('log_id');
    if (idInput) idInput.value = "";

    const manualInput = document.getElementById('manual_credit');
    if (manualInput) manualInput.value = "";

    const dateInput = document.getElementById('log_date');
    if (dateInput) dateInput.value = window.OJT_CONFIG?.today || "";

    const title = document.getElementById('form-title');
    if (title) title.innerText = "New Entry";

    const submitBtn = document.getElementById('submit-btn');
    if (submitBtn) submitBtn.innerText = "Log Session";

    const cancelBtn = document.getElementById('cancel-edit');
    if (cancelBtn) cancelBtn.classList.add('hidden');
    
    checkDateRestrictions();
};

window.quickFill = function() {
    const is10hMode = document.getElementById('cfg-10h')?.checked;
    
    if (is10hMode) {
        document.getElementById('am_in').value = "07:00"; 
        document.getElementById('am_out').value = "12:00";
        document.getElementById('pm_in').value = "13:00"; 
        document.getElementById('pm_out').value = "18:00"; 
    } else {
        document.getElementById('am_in').value = "08:00"; 
        document.getElementById('am_out').value = "12:00";
        document.getElementById('pm_in').value = "13:00"; 
        document.getElementById('pm_out').value = "17:00";
    }
};

window.setHalfDay = function(shift) {
    if (shift === 'AM') {
        document.getElementById('am_in').value = "08:00"; document.getElementById('am_out').value = "12:00";
        document.getElementById('pm_in').value = ""; document.getElementById('pm_out').value = "";
    } else {
        document.getElementById('am_in').value = ""; document.getElementById('am_out').value = "";
        document.getElementById('pm_in').value = "13:00"; document.getElementById('pm_out').value = "17:00";
    }
};

window.setAbsent = function() {
    ['am_in', 'am_out', 'pm_in', 'pm_out'].forEach(id => document.getElementById(id).value = "");
};

window.confirmDelete = async function(e, url) {
    e.preventDefault();
    e.stopPropagation(); // Prevents tooltip from triggering

    if (confirm("Permanently delete this session log?")) {
        try {
            await fetch(url);
            // Refresh components
            const response = await fetch(window.location.href);
            const html = await response.text();
            const doc = new DOMParser().parseFromString(html, 'text/html');

            ['stats-container', 'archive-container', 'intelligence-container'].forEach(id => {
                const oldEl = document.getElementById(id);
                const newEl = doc.getElementById(id);
                if (oldEl && newEl) oldEl.innerHTML = newEl.innerHTML;
            });

            lucide.createIcons();
            // Re-apply collapse state logic if needed
        } catch (err) {
            alert("Error deleting record.");
        }
    }
};

window.toggleConfigAvailability = function() {
    const isStrict = document.getElementById('master-strict')?.checked;
    const subRulesContainer = document.getElementById('sub-rules-container');
    if(!subRulesContainer) return;
    
    const subInputs = subRulesContainer.querySelectorAll('.sub-config');
    const rows = subRulesContainer.querySelectorAll('.config-row');

    if (isStrict) {
        subRulesContainer.style.opacity = '0.3';
        subRulesContainer.style.pointerEvents = 'none';
        subInputs.forEach(input => input.disabled = true);
        rows.forEach(row => row.classList.add('grayscale'));
    } else {
        subRulesContainer.style.opacity = '1';
        subRulesContainer.style.pointerEvents = 'auto';
        subInputs.forEach(input => input.disabled = false);
        rows.forEach(row => row.classList.remove('grayscale'));
    }
    checkDateRestrictions();
};

window.captureSnippet = async function() {
    const card = document.getElementById('stats-container');
    const btn = event.currentTarget;
    const originalContent = btn.innerHTML;
    
    btn.innerHTML = '<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i>';
    lucide.createIcons();

    try {
        const canvas = await html2canvas(card, {
            backgroundColor: '#020617',
            scale: 3,
            useCORS: true,
            logging: false,
            onclone: (clonedDoc) => {
                const watermark = clonedDoc.querySelector('.snippet-visible');
                if (watermark) {
                    watermark.classList.remove('hidden');
                    watermark.style.display = 'block';
                }
            }
        });

        const image = canvas.toDataURL("image/png", 1.0);
        const link = document.createElement('a');
        link.download = `OJT-Status-LHA-${new Date().toLocaleDateString()}.png`;
        link.href = image;
        link.click();

        btn.innerHTML = '<i data-lucide="check" class="w-4 h-4 text-emerald-400"></i>';
    } catch (err) {
        console.error("Snippet failed:", err);
        btn.innerHTML = '<i data-lucide="alert-circle" class="w-4 h-4 text-rose-400"></i>';
    }

    setTimeout(() => {
        btn.innerHTML = originalContent;
        lucide.createIcons();
    }, 2000);
};

// --- LIVE SESSION LOGIC ---

function updateClock() {
    const clockEl = document.getElementById('live-clock');
    if (clockEl) {
        clockEl.innerText = new Date().toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    }
}

window.handlePunch = async function() {
    const btn = document.getElementById('punch-btn');
    if(!btn) return;
    btn.disabled = true;
    btn.innerHTML = '<i data-lucide="loader-2" class="w-4 h-4 animate-spin"></i>';
    lucide.createIcons();

    try {
        await fetch('/punch', { method: 'POST' });
        const response = await fetch(window.location.href);
        const html = await response.text();
        const doc = (new DOMParser()).parseFromString(html, 'text/html');

        ['stats-container', 'intelligence-container', 'eta-container', 'archive-container', 'section-live'].forEach(id => {
            const el = document.getElementById(id);
            if(el) el.innerHTML = doc.getElementById(id).innerHTML;
        });

        lucide.createIcons();
        checkDateRestrictions(); 
    } catch (err) {
        console.error(err);
        btn.disabled = false;
    }
};

window.openInbox = async function() {
    const modal = document.getElementById('inbox-modal');
    if(modal) modal.showModal();
    const badge = document.getElementById('nav-unread-badge');
    if (badge) badge.style.display = 'none';
    
    try {
        await fetch('/notifications/mark-read', { 
            method: 'POST',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        });
    } catch (err) {
        console.error("Failed to clear notifications", err);
    }
};

// Initial boot
document.addEventListener('DOMContentLoaded', () => {
    updateClock();
    setInterval(updateClock, 1000);
    toggleConfigAvailability();
    checkDateRestrictions();
});

document.addEventListener('DOMContentLoaded', () => {
    const strict8h = document.getElementById('master-strict');
    const mode10h = document.getElementById('cfg-10h');

    if (strict8h && mode10h) {
        mode10h.addEventListener('change', () => {
            if (mode10h.checked) {
                strict8h.checked = false; // Uncheck Strict 8h
                toggleConfigAvailability(); // Update UI dimming
            }
        });

        strict8h.addEventListener('change', () => {
            if (strict8h.checked) {
                mode10h.checked = false; // Uncheck Compressed 10h
            }
        });
    }
});
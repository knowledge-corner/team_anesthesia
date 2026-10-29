const { chromium, devices } = require('/opt/node22/lib/node_modules/playwright');
const B = 'http://127.0.0.1:8130';
const OUT = 'shots/';
const HL = 'outline:3px solid #e11d48 !important; outline-offset:2px !important; border-radius:6px;';
(async () => {
  const browser = await chromium.launch();
  async function ctx(opts = {}) {
    const c = await browser.newContext({ ...devices['iPhone 13'], locale: 'en-IN', timezoneId: 'Asia/Kolkata', ...opts });
    await c.addInitScript(() => {
      // Show the Android-only "Pick from phone contacts" button for the manual
      window.ContactsManager = function () {};
      navigator.contacts = { select: async () => [{ name: ['Mr. Rajesh Kamble'], tel: ['+91 98500 55555'] }] };
      try { localStorage.setItem('push-prompt-dismissed', '1'); } catch (e) {}
    });
    return c;
  }
  const errors = [];
  async function shot(p, name, { hl = [], scroll = null, full = false, wait = 300 } = {}) {
    try {
      if (scroll) { await p.locator(scroll).first().scrollIntoViewIfNeeded(); await p.evaluate(() => window.scrollBy(0, -90)); }
      await p.evaluate(([sels, css]) => {
        document.querySelectorAll('[data-hl]').forEach(e => { e.style.cssText = e.dataset.prev || ''; e.removeAttribute('data-hl'); });
        sels.forEach(s => document.querySelectorAll(s).forEach(e => { e.dataset.prev = e.style.cssText; e.setAttribute('data-hl', '1'); e.style.cssText += css; }));
      }, [hl, HL]);
      if (full) await p.addStyleTag({ content: '.bottom-nav,.form-actions,.sticky-top{position:static!important}' });
      await p.waitForTimeout(wait);
      await p.screenshot({ path: OUT + name + '.png', fullPage: full });
    } catch (e) { errors.push(name + ': ' + e.message.split('\n')[0]); }
  }
  async function login(p, u, pw = 'Demo@12345') {
    await p.goto(B + '/login/'); await p.fill('#id_username', u); await p.fill('#id_password', pw);
    await Promise.all([p.waitForURL(x => !x.pathname.startsWith('/login')), p.click('form button.btn-primary')]);
  }
  const step = async (name, fn) => { try { await fn(); } catch (e) { errors.push(name + ': ' + e.message.split('\n')[0]); } };

  // ---------- Signed out ----------
  let c = await ctx(); let p = await c.newPage();
  await step('login', async () => { await p.goto(B + '/login/'); await shot(p, '01-login', { hl: ['a[href="/forgot-user-id/"]', 'a[href="/password-reset/"]', 'a[href="/signup/"]'] }); });
  await step('signup', async () => { await p.goto(B + '/signup/'); await shot(p, '02-signup', { full: true }); });
  await step('forgotid', async () => {
    await p.goto(B + '/forgot-user-id/'); await p.fill('#id_mobile', '98220 12345'); await shot(p, '03-forgot-id');
    await p.click('form button.btn-primary'); await p.waitForLoadState(); await shot(p, '04-forgot-id-result');
  });
  await step('forgotpw', async () => {
    await p.goto(B + '/password-reset/'); await p.fill('#id_username', 'dr.anjali'); await p.fill('#id_mobile', '9822012345');
    await shot(p, '05-forgot-password');
    await p.click('form button.btn-primary'); await p.waitForLoadState(); await shot(p, '06-set-new-password');
  });
  await c.close();

  // ---------- Doctor ----------
  c = await ctx(); p = await c.newPage();
  await login(p, 'dr.anjali');
  await step('dash', async () => {
    await p.goto(B + '/'); await shot(p, '10-dashboard', { hl: ['.chips, .period-chips'] });
    await shot(p, '11-dashboard-cards', { scroll: 'a.stat-link >> nth=1', hl: ['a.stat-link'] });
    await shot(p, '12-dashboard-action', { scroll: 'text=Action required' });
    await p.click('.account-btn'); await shot(p, '13-profile-menu', { hl: ['a[href="/password/"]'] });
    await p.goto(B + '/password/'); await shot(p, '14-change-password');
  });
  // Add case
  await step('add', async () => {
    await p.goto(B + '/cases/add/'); await shot(p, '20-add-case', { hl: ['#id_doctor', 'a[href="/cases/import/"]'] });
    await p.selectOption('#id_doctor', { label: 'Dr. Vikram Rao' }); await shot(p, '20b-colleague', { hl: ['#id_doctor'] });
    await p.selectOption('#id_doctor', { index: 0 });
    await p.click('#id_hospital_search'); await p.fill('#id_hospital_search', 'ruby'); await p.waitForTimeout(900);
    await shot(p, '21-hospital-search', { hl: ['.combo-add'] });
    await p.fill('#id_hospital_search', 'jehangeer'); await p.waitForTimeout(1200);
    await shot(p, '21b-did-you-mean', { hl: ['.combo-group'] });
    await p.fill('#id_hospital_search', 'ruby'); await p.waitForTimeout(1200);
    await p.click('.combo-item >> nth=0'); await p.waitForTimeout(900);
    await p.fill('#id_fee', '9000'); await p.fill('#id_patient_name', 'Mohan Patil');
    await shot(p, '22-add-case-filled', { scroll: '#id_case_date', hl: ['#id_surgeon_search', '#id_patient_name'] });
    await p.click('#new-surgeon-toggle'); await p.fill('#id_new_surgeon_name', 'Dr. Vivek Rane');
    await shot(p, '23-new-surgeon', { scroll: '#id_surgeon_search', hl: ['#new-surgeon-fields'] });
    await p.click('#new-surgeon-toggle');
    await p.click('#new-contact-toggle');
    await shot(p, '24-new-contact', { scroll: '#id_contact_search', hl: ['#new-contact-fields [data-contact-pick]'] });
    await p.click('#new-contact-fields [data-contact-pick]'); await p.waitForTimeout(300);
    await shot(p, '25-contact-picked', { scroll: '#id_contact_search', hl: ['#id_new_contact_name', '#id_new_contact_phone'] });
    await p.fill('#id_new_contact_name', ''); await p.fill('#id_new_contact_phone', ''); await p.click('#new-contact-toggle');
    await p.fill('#id_procedure_type', 'TKR - spinal'); await p.fill('#id_patient_reference', 'IP 51010');
    await p.evaluate(() => { const e = document.getElementById('id_paid_now'); if (!e.checked) e.click(); }); await p.waitForTimeout(200);
    await shot(p, '26-add-case-lower', { scroll: '#id_procedure_type', hl: ['#id_due_date', '#id_paid_now'] });
    await p.evaluate(() => { const e = document.getElementById('id_paid_now'); if (e.checked) e.click(); });
    await p.click('button[name=save]'); await p.waitForSelector('#due-date-modal.show');
    await shot(p, '27-due-date-popup', { wait: 500 });
    await Promise.all([p.waitForURL(u => !u.pathname.startsWith('/cases/add')), p.click('#due-date-ok')]);
    await shot(p, '28-case-saved');
  });
  await step('addhospital', async () => {
    await p.goto(B + '/hospitals/add/?next=/cases/add/&name=Shree%20Clinic'); await p.fill('#id_city', 'Pune'); await p.fill('#id_area', 'Baner');
    await shot(p, '29-add-hospital');
    await p.goto(B + '/hospitals/add/?next=/cases/add/&name=Sahyadri%20Kothrud%20Hospital'); await p.fill('#id_city', 'Pune');
    await shot(p, '29b-is-it-one-of-these', { hl: ['#similar-hospitals'] });
  });
  // Bulk upload
  await step('bulk', async () => {
    await p.goto(B + '/cases/import/'); await shot(p, '30-bulk-upload', { hl: ['a[href="/cases/import/template/"]'] });
    await p.setInputFiles('#id_file', 'bad_upload.xlsx'); await p.click('form button.btn-primary'); await p.waitForLoadState();
    await p.evaluate(() => { const el = document.querySelector('.alert-danger'); window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 70); });
    await shot(p, '31-bulk-errors', { hl: ['.cell-error'] });
  });
  // Cases
  await step('cases', async () => {
    await p.goto(B + '/cases/'); await shot(p, '40-cases-list', { hl: ['select[name="doctor"]'] });
    await p.goto(B + '/cases/?status=unpaid'); await shot(p, '41-cases-unpaid');
  });
  const caseUrl = await p.evaluate(async (B) => { const r = await fetch('/cases/?q=Deshmukh'); const t = await r.text(); const m = t.match(/href="(\/cases\/\d+\/)"/); return m ? m[1] : null; }, B);
  await step('detail', async () => {
    await p.goto(B + caseUrl); await shot(p, '42-case-detail', { hl: ['a[href$="/edit/"]', 'a[href$="/delete/"]'] });
    await shot(p, '43-case-detail-lower', { scroll: 'text=Follow-ups', hl: ['.alert.small'] });
  });
  await step('pay', async () => {
    const id = caseUrl.match(/\d+/)[0];
    await p.goto(B + '/payments/record/case/' + id + '/'); await shot(p, '44-record-payment', { hl: ['#id_received_by'] });
    await p.goto(B + '/payments/case/' + id + '/follow-up/');
    await p.fill('#id_notes', 'Bill is with accounts, will pay next week');
    const d = new Date(); d.setDate(d.getDate() + 7); const iso = d.toISOString().slice(0, 10);
    await p.fill('#id_promised_payment_date', iso); await p.fill('#id_next_reminder', iso);
    await p.evaluate(() => { const el = document.getElementById('id_notes'); window.scrollTo(0, el.getBoundingClientRect().top + window.scrollY - 120); });
    await shot(p, '45-follow-up', { hl: ['#id_next_reminder'] });
    await p.goto(B + '/cases/' + id + '/edit/'); await shot(p, '46-edit-case', { hl: ['.form-actions a[href$="/delete/"]'] });
    await p.goto(B + '/cases/' + id + '/delete/'); await shot(p, '46b-delete-confirm', { hl: ['button.btn-danger'] });
  });
  await step('recv', async () => {
    await p.goto(B + '/receivables/'); await shot(p, '47-outstanding');
    await p.goto(B + '/receivables/?view=overdue'); await shot(p, '48-overdue');
    await p.goto(B + '/receivables/?view=followup');
    const dd = p.locator('.list-group-item [data-bs-toggle="dropdown"]').first();
    if (await dd.count()) { await dd.click(); }
    await shot(p, '49-followup-menu', { hl: ['.dropdown-menu.show'] });
  });
  // Hospitals
  await step('hosp', async () => {
    await p.goto(B + '/hospitals/'); await shot(p, '50-hospitals');
    await p.goto(B + '/hospitals/?q=kem'); await shot(p, '51-hospital-search');
    await p.goto(B + '/hospitals/'); await p.click('.list-group a >> nth=0'); await p.waitForLoadState(); await shot(p, '52-hospital-detail', { full: true });
  });
  // Contacts & surgeons
  await step('contacts', async () => {
    await p.goto(B + '/contacts/'); await shot(p, '60-contacts', { hl: ['.nav-pills'] });
    await p.click('.list-group-item a >> nth=0'); await p.waitForLoadState(); await shot(p, '61-contact-detail', { full: true });
    await p.goto(B + '/contacts/add/'); await shot(p, '62-add-contact', { hl: ['[data-contact-pick]'] });
    await p.goto(B + '/contacts/surgeons/'); await shot(p, '63-surgeons');
    await p.click('.list-group-item a >> nth=0'); await p.waitForLoadState(); await shot(p, '64-surgeon-detail', { full: true });
    await p.goto(B + '/contacts/surgeons/add/'); await shot(p, '65-add-surgeon');
  });
  // Reports
  await step('reports', async () => {
    await p.goto(B + '/reports/'); await shot(p, '70-reports');
    await p.goto(B + '/reports/cases/?period=last_3'); await shot(p, '71-cases-report', { hl: ['a[href*="export=xlsx"]'] });
    await p.goto(B + '/reports/monthly/?period=last_12'); await shot(p, '72-monthly', { scroll: 'table', hl: ['table tbody tr:first-child a'] });
    await p.click('table tbody a >> nth=1'); await p.waitForLoadState(); await shot(p, '73-month-page');
    await p.goto(B + '/reports/hospitals/?period=all'); await shot(p, '74-hospital-wise', { scroll: '.chips' });
    await p.goto(B + '/reports/surgeons/?period=all'); await shot(p, '75-surgeon-hospital', { scroll: '.list-group' });
    await p.goto(B + '/reports/payments/?period=last_3'); await shot(p, '76-payment-history', { scroll: '.stat-card' });
  });
  await step('notif', async () => { await p.goto(B + '/notifications/'); await shot(p, '80-notifications', { full: true, hl: ['form[action="/notifications/scope/"] select'] }); });
  await c.close();

  // ---------- Administrator login ----------
  c = await ctx(); p = await c.newPage();
  await step('admin', async () => {
    await p.goto(B + '/login/'); await p.fill('#id_username', 'admin'); await p.fill('#id_password', 'Admin@12345');
    await shot(p, '90-admin-login', { hl: ['#id_username', '#id_password'] });
    await Promise.all([p.waitForURL(x => !x.pathname.startsWith('/login')), p.click('form button.btn-primary')]);
    await shot(p, '91-admin-dashboard');
    await p.click('.account-btn'); await shot(p, '92-admin-menu', { hl: ['a[href="/doctors/"]', 'a[href="/settings/"]', 'a[href="/hospitals/directory/import/"]'] });
    await p.goto(B + '/doctors/'); await shot(p, '93-doctors', { hl: ['a[href="/doctors/add/"]'] });
    await p.click('.list-group a >> nth=0'); await p.waitForLoadState(); await shot(p, '94-doctor-edit');
    await p.goto(B + '/cases/'); await shot(p, '95-admin-cases', { hl: ['select[name="doctor"]'] });
    await p.goto(B + '/cases/add/'); await shot(p, '96-admin-add-case', { hl: ['#id_doctor, #id_doctor_search'] });
    await p.goto(B + '/settings/'); await shot(p, '97-settings');
    await p.goto(B + '/hospitals/directory/import/'); await shot(p, '98-directory-import');
    await p.goto(B + '/hospitals/duplicates/'); await shot(p, '99-duplicates', { hl: ['form[action="/hospitals/merge/"] .btn-primary'] });
    await Promise.all([p.waitForLoadState(), p.click('form[action="/hospitals/merge/"] button.btn-primary >> nth=0')]);
    await shot(p, '99b-merge-confirm', { hl: ['.form-actions .btn-primary'] });
  });
  console.log('ERRORS:\n' + errors.join('\n'));
  await browser.close();
})();

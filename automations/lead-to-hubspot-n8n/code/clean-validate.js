// n8n Code node "Clean & validate lead" (Run Once for All Items).
// Normalises a raw form/ad lead into HubSpot-ready fields and flags bad data.
// Input: webhook items ({ body: {...} }). Output: { valid, errors, warnings, lead }.

const FREE_EMAIL_DOMAINS = new Set([
  'gmail.com', 'googlemail.com', 'yahoo.com', 'yahoo.co.uk', 'hotmail.com', 'outlook.com', 'live.com',
  'icloud.com', 'me.com', 'aol.com', 'proton.me', 'protonmail.com', 'gmx.com', 'mail.com', 'yandex.com',
]);
const COUNTRIES = {
  us: 'United States', usa: 'United States', 'united states': 'United States', 'united states of america': 'United States',
  uk: 'United Kingdom', gb: 'United Kingdom', 'great britain': 'United Kingdom', england: 'United Kingdom',
  'united kingdom': 'United Kingdom', ca: 'Canada', canada: 'Canada', au: 'Australia', australia: 'Australia',
  de: 'Germany', germany: 'Germany', fr: 'France', france: 'France', ug: 'Uganda', uganda: 'Uganda',
  ke: 'Kenya', kenya: 'Kenya', ng: 'Nigeria', nigeria: 'Nigeria', in: 'India', india: 'India',
};
const EMAIL = /^[^\s@]+@[^\s@]+\.[a-z]{2,}$/i;

const text = (value) => (value === undefined || value === null ? '' : String(value).replace(/\s+/g, ' ').trim());
const titleCase = (value) => value.toLowerCase().replace(/(^|[\s'’-])(\p{L})/gu, (_, sep, ch) => sep + ch.toUpperCase());

function normalisePhone(raw, country, warnings) {
  const value = text(raw);
  if (!value) return '';
  const digits = value.replace(/\D/g, '');
  if (value.startsWith('+') && digits.length >= 8 && digits.length <= 15) return `+${digits}`;
  if (value.startsWith('00') && digits.length >= 10) return `+${digits.slice(2)}`;
  if (country === 'United States' || country === 'Canada') {
    if (digits.length === 10) return `+1${digits}`;
    if (digits.length === 11 && digits.startsWith('1')) return `+${digits}`;
  }
  warnings.push(`phone "${value}" kept as-is: add a country code to standardise it`);
  return value;
}

function normaliseWebsite(raw) {
  const value = text(raw).toLowerCase();
  return value.replace(/^https?:\/\//, '').replace(/^www\./, '').replace(/\/+$/, '');
}

const results = [];
for (const item of $input.all()) {
  const body = item.json.body ?? item.json;
  const errors = [];
  const warnings = [];

  const email = text(body.email).toLowerCase();
  if (!email) errors.push('email is required');
  else if (!EMAIL.test(email)) errors.push(`email "${email}" is not a valid address`);

  let first = text(body.first_name ?? body.firstname ?? body.firstName);
  let last = text(body.last_name ?? body.lastname ?? body.lastName);
  const full = text(body.name ?? body.full_name ?? body.fullName);
  if (!first && full) {
    const parts = full.split(' ');
    first = parts.shift();
    last = last || parts.join(' ');
  }
  if (!first) warnings.push('no first name supplied');

  const rawCountry = text(body.country);
  const country = COUNTRIES[rawCountry.toLowerCase()] ?? (rawCountry ? titleCase(rawCountry) : '');
  const utm = body.utm ?? {};
  const domain = email.includes('@') ? email.split('@')[1] : '';

  const lead = {
    email,
    firstname: first ? titleCase(first) : '',
    lastname: last ? titleCase(last) : '',
    phone: normalisePhone(body.phone, country, warnings),
    company: text(body.company),
    jobtitle: text(body.job_title ?? body.jobtitle ?? body.title),
    website: normaliseWebsite(body.website) || (domain && !FREE_EMAIL_DOMAINS.has(domain) ? domain : ''),
    country,
    employees: Number.parseInt(text(body.employees ?? body.company_size).replace(/[^\d]/g, ''), 10) || null,
    budget: Number.parseInt(text(body.budget).replace(/[^\d]/g, ''), 10) || null,
    form: text(body.form ?? body.form_type).toLowerCase() || 'unknown',
    message: text(body.message),
    utm_source: text(body.utm_source ?? utm.source).toLowerCase(),
    utm_medium: text(body.utm_medium ?? utm.medium).toLowerCase(),
    utm_campaign: text(body.utm_campaign ?? utm.campaign).toLowerCase(),
    marketing_consent: body.marketing_consent === true || ['yes', 'true', '1', 'on'].includes(text(body.marketing_consent).toLowerCase()),
    email_domain: domain,
    free_email: FREE_EMAIL_DOMAINS.has(domain),
  };

  results.push({ json: { valid: errors.length === 0, errors, warnings, lead, received_at: new Date().toISOString() } });
}
return results;

// n8n Code node "Score lead" (Run Once for All Items).
// Transparent rule-based scoring: every point comes with a reason, so sales
// can see why a lead was routed the way it was. Thresholds live in Config.

const config = $('Config').first().json;

function score(lead) {
  const reasons = [];
  let points = 0;
  const add = (value, why) => {
    points += value;
    reasons.push(`+${value} ${why}`);
  };

  if (lead.form === 'demo_request' || lead.form === 'demo') add(25, 'asked for a demo');
  else if (lead.form === 'contact_sales') add(20, 'contacted sales');
  if (!lead.free_email && lead.email_domain) add(20, 'business email');

  const title = lead.jobtitle.toLowerCase();
  if (/\b(ceo|cmo|cto|coo|cfo|chief|founder|co-founder|owner|president|vp|vice president|head|director)\b/.test(title)) {
    add(30, `senior title (${lead.jobtitle})`);
  } else if (/\b(manager|lead|principal)\b/.test(title)) {
    add(15, `manager-level title (${lead.jobtitle})`);
  }

  if (lead.employees >= 200) add(25, `${lead.employees} employees`);
  else if (lead.employees >= 50) add(15, `${lead.employees} employees`);
  if (lead.budget >= 5000) add(20, `budget ${lead.budget}`);
  if (['referral', 'partner'].includes(lead.utm_medium)) add(10, `${lead.utm_medium} traffic`);
  if (lead.message.length >= 40) add(5, 'wrote a detailed message');

  points = Math.min(points, 100);
  const tier = points >= config.hotScore ? 'hot' : points >= config.warmScore ? 'warm' : 'cold';
  return { score: points, tier, reasons };
}

return $input.all().map((item) => ({ json: { ...item.json, ...score(item.json.lead) } }));

// n8n Code node "Merge with existing contact" (Run Once for Each Item).
// Decides create vs update and builds the HubSpot properties so that:
//  - existing good data is never wiped by a blank form field
//  - lifecycle stage only ever moves forward (HubSpot rejects going backwards)
//  - latest attribution (UTMs) and the lead score are always refreshed

const STAGES = ['subscriber', 'lead', 'marketingqualifiedlead', 'salesqualifiedlead', 'opportunity', 'customer', 'evangelist'];
const PROTECTED_IF_SET = ['firstname', 'lastname', 'company', 'jobtitle', 'website', 'country'];

const { lead, score, tier, reasons, warnings } = $('Score lead').item.json;
const existing = $input.item.json.results?.[0] ?? null;
const current = existing?.properties ?? {};

const props = {
  email: lead.email,
  lead_score: String(score),
  lead_tier: tier,
};
for (const key of ['firstname', 'lastname', 'phone', 'company', 'jobtitle', 'website', 'country']) {
  if (!lead[key]) continue; // never overwrite with blanks
  if (existing && PROTECTED_IF_SET.includes(key) && current[key]) continue; // keep what sales already has
  props[key] = lead[key];
}
for (const key of ['utm_source', 'utm_medium', 'utm_campaign']) {
  if (lead[key]) props[`latest_${key}`] = lead[key];
}
if (lead.marketing_consent) props.marketing_consent = 'true';

const wanted = tier === 'hot' ? 'marketingqualifiedlead' : 'lead';
const currentStage = STAGES.indexOf(current.lifecyclestage ?? '');
if (STAGES.indexOf(wanted) > currentStage) props.lifecyclestage = wanted;
if (!existing) props.hs_lead_status = 'NEW';

return {
  json: {
    action: existing ? 'update' : 'create',
    contactId: existing?.id ?? null,
    properties: props,
    score,
    tier,
    reasons,
    warnings,
  },
};

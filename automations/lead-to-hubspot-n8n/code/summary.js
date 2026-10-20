// n8n Code node "Result summary" (Run Once for Each Item).
// Runs after either the create or the update call and builds the response
// returned to the form plus the data used for routing.

const plan = $('Merge with existing contact').item.json;

return {
  json: {
    status: 'ok',
    action: plan.action === 'create' ? 'created' : 'updated',
    contactId: String($input.item.json.id ?? plan.contactId),
    email: plan.properties.email,
    score: plan.score,
    tier: plan.tier,
    reasons: plan.reasons,
    warnings: plan.warnings,
  },
};

// Assign 'Cognitive Services OpenAI User' on the Foundry / Azure OpenAI account
// to the user-assigned managed identity. Scope is the Foundry account itself
// (least-privilege — does not grant anything outside that account).
@description('Name of the existing Azure AI Foundry / Azure OpenAI account.')
param foundryAccountName string

@description('Object (principal) ID of the managed identity to grant access.')
param principalId string

// Built-in role definition ID for 'Cognitive Services OpenAI User'.
// See https://learn.microsoft.com/azure/ai-services/openai/how-to/role-based-access-control
var openAiUserRoleId = '5e0bd9bd-7b93-4f28-af87-19fc36ad61bd'

resource foundryAccount 'Microsoft.CognitiveServices/accounts@2024-10-01' existing = {
  name: foundryAccountName
}

resource roleAssignment 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  // Deterministic GUID so re-deploys are idempotent.
  name: guid(foundryAccount.id, principalId, openAiUserRoleId)
  scope: foundryAccount
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', openAiUserRoleId)
    principalId: principalId
    principalType: 'ServicePrincipal'
  }
}

output roleAssignmentId string = roleAssignment.id

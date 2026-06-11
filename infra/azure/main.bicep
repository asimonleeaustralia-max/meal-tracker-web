// MealTracker — Azure Bicep deployment
//
// Provisions everything for the microservices backend:
//   * Resource group (passed in)
//   * Log Analytics workspace
//   * Container Apps Environment (Consumption plan, scale-to-zero)
//   * Azure Container Registry (Basic SKU, cheapest)
//   * PostgreSQL Flexible Server, Burstable B1ms (cheapest)
//   * Storage account + blob container for meal photos
//   * One Container App per service
//
// Deploy with:
//   az deployment group create \
//       -g <resource-group> \
//       -f infra/azure/main.bicep \
//       -p infra/azure/parameters.json

@description('Azure region')
param location string = resourceGroup().location

@description('Short prefix used to compose resource names (lowercase, 3-12 chars)')
@minLength(3)
@maxLength(20)
param namePrefix string = 'mealtracker'

@description('Postgres admin user')
param pgAdminUser string = 'mealadmin'

@description('Postgres admin password (Key Vault reference recommended)')
@secure()
param pgAdminPassword string

@description('JWT shared secret (Key Vault reference recommended)')
@secure()
param jwtSecret string

@description('Container image tag to deploy (e.g. "v1" or git SHA)')
param imageTag string = 'latest'

@description('Google OAuth client ID (empty disables Google login)')
param googleClientId string = ''
@secure()
param googleClientSecret string = ''

@description('Apple Sign-In Services ID (empty disables Apple web login)')
param appleClientId string = ''
@description('iOS bundle ID for native Sign in with Apple token verification')
param appleIosClientId string = ''
@description('Apple Developer Team ID (web OAuth client secret)')
param appleTeamId string = ''
@description('Sign in with Apple key ID (web OAuth)')
param appleKeyId string = ''
@secure()
param applePrivateKey string = ''

@description('Facebook app ID (empty disables Facebook login)')
param facebookClientId string = ''
@secure()
param facebookClientSecret string = ''

@description('RunPod serverless endpoint URL (.../runsync) — empty enables stub mode')
param runpodEndpointUrl string = ''
@secure()
param runpodApiKey string = ''

@description('Public web URL used in password-reset emails')
param passwordResetBaseUrl string = 'https://macrossimple.com'

@description('Custom apex web hostname (TLS via managed certificate)')
param customWebHostname string = 'macrossimple.com'

@description('Custom API gateway hostname (TLS via managed certificate)')
param customApiHostname string = 'api.macrossimple.com'


// ───── Composed names ─────
var pgServerName     = '${namePrefix}-pg'
var pgDbName         = 'mealtracker'
var registryName     = toLower(replace('${namePrefix}acr', '-', ''))
// Storage account names must be 3-24 chars, lowercase alphanumeric only.
// Truncate (not substring with a hard length) so any namePrefix length works.
var storageNameRaw   = toLower(replace('${namePrefix}stg', '-', ''))
var storageName      = length(storageNameRaw) > 24 ? substring(storageNameRaw, 0, 24) : storageNameRaw
var envName          = '${namePrefix}-env'
var workspaceName    = '${namePrefix}-logs'
var blobContainerName = 'meal-photos'


// ───── Observability ─────
resource workspace 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: workspaceName
  location: location
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

// ───── Container Registry (Basic SKU = cheapest) ─────
resource acr 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: registryName
  location: location
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: true   // simplest; switch to managed identity later
  }
}

// ───── PostgreSQL Flexible Server (B1ms = cheapest burstable) ─────
resource postgres 'Microsoft.DBforPostgreSQL/flexibleServers@2024-08-01' = {
  name: pgServerName
  location: location
  sku: {
    name: 'Standard_B1ms'
    tier: 'Burstable'
  }
  properties: {
    version: '16'
    administratorLogin: pgAdminUser
    administratorLoginPassword: pgAdminPassword
    storage: {
      storageSizeGB: 32
      autoGrow: 'Enabled'
    }
    backup: {
      backupRetentionDays: 7
      geoRedundantBackup: 'Disabled'
    }
    highAvailability: { mode: 'Disabled' }
    network: {
      publicNetworkAccess: 'Enabled'
    }
  }
}

// Allow Azure-internal services (incl. Container Apps) to connect
resource pgAllowAzure 'Microsoft.DBforPostgreSQL/flexibleServers/firewallRules@2024-08-01' = {
  parent: postgres
  name: 'AllowAllAzureIPs'
  properties: {
    startIpAddress: '0.0.0.0'
    endIpAddress: '0.0.0.0'
  }
}

// Required Postgres extensions
resource pgExtensions 'Microsoft.DBforPostgreSQL/flexibleServers/configurations@2024-08-01' = {
  parent: postgres
  name: 'azure.extensions'
  properties: {
    value: 'PG_TRGM,UUID-OSSP'
    source: 'user-override'
  }
}

resource pgDatabase 'Microsoft.DBforPostgreSQL/flexibleServers/databases@2024-08-01' = {
  parent: postgres
  name: pgDbName
  properties: { charset: 'UTF8', collation: 'en_US.utf8' }
}

// ───── Storage account for meal photos ─────
resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    accessTier: 'Hot'
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
  }
}
resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}
resource photoContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: blobContainerName
  properties: { publicAccess: 'None' }
}

// ───── Container Apps Environment (Consumption workload profile) ─────
resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: envName
  location: location
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: workspace.properties.customerId
        sharedKey: workspace.listKeys().primarySharedKey
      }
    }
    workloadProfiles: [
      {
        name: 'Consumption'
        workloadProfileType: 'Consumption'
      }
    ]
  }
}

// ───── Shared env vars assembled once ─────
var dbHost = '${pgServerName}.postgres.database.azure.com'
// Note: the values below flow into @secure() Container App secrets, but
// @secure() only applies to params/outputs (not variables). The
// `use-secure-value-for-secure-inputs` warnings on the secret assignments
// below are cosmetic — Container Apps still treats the values as secure.
var commonDbUrl = 'postgresql+asyncpg://${pgAdminUser}:${pgAdminPassword}@${dbHost}:5432/${pgDbName}?ssl=require'
var blobAccountUrl = 'https://${storage.name}.blob.${environment().suffixes.storage}'
var storageKey = storage.listKeys().keys[0].value
var acrPassword = acr.listCredentials().passwords[0].value

// ───── Per-service Container Apps ─────
// auth-service
resource authApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-auth'
  location: location
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: '${acr.name}.azurecr.io', username: acr.name, passwordSecretRef: 'acr-password' }]
      secrets: concat(
        [
          { name: 'acr-password', value: acrPassword }
          { name: 'database-url', value: commonDbUrl }
          { name: 'jwt-secret',   value: jwtSecret }
        ],
        empty(googleClientSecret)   ? [] : [{ name: 'google-secret',   value: googleClientSecret }],
        empty(applePrivateKey)      ? [] : [{ name: 'apple-key',       value: applePrivateKey }],
        empty(facebookClientSecret) ? [] : [{ name: 'facebook-secret', value: facebookClientSecret }]
      )
      ingress: {
        external: false
        targetPort: 8001
        transport: 'http'
      }
    }
    template: {
      containers: [{
        name: 'auth-service'
        image: '${acr.name}.azurecr.io/mealtracker/auth-service:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: concat(
          [
            { name: 'ENVIRONMENT',     value: 'production' }
            { name: 'DATABASE_URL',    secretRef: 'database-url' }
            { name: 'DB_SCHEMA',       value: 'auth' }
            { name: 'JWT_SECRET',      secretRef: 'jwt-secret' }
            { name: 'SESSION_SECRET',  secretRef: 'jwt-secret' }
            { name: 'GOOGLE_CLIENT_ID',   value: googleClientId }
            { name: 'APPLE_CLIENT_ID',     value: appleClientId }
            { name: 'APPLE_IOS_CLIENT_ID', value: appleIosClientId }
            { name: 'APPLE_TEAM_ID',       value: appleTeamId }
            { name: 'APPLE_KEY_ID',        value: appleKeyId }
            { name: 'FACEBOOK_CLIENT_ID', value: facebookClientId }
            { name: 'PASSWORD_RESET_BASE_URL', value: passwordResetBaseUrl }
            { name: 'GOOGLE_REDIRECT_URI', value: 'https://${customApiHostname}/api/auth/oauth/google/callback' }
            { name: 'APPLE_REDIRECT_URI', value: 'https://${customApiHostname}/api/auth/oauth/apple/callback' }
            { name: 'FACEBOOK_REDIRECT_URI', value: 'https://${customApiHostname}/api/auth/oauth/facebook/callback' }
            { name: 'OAUTH_SUCCESS_REDIRECT', value: 'https://${customWebHostname}/auth/success' }
            { name: 'OAUTH_FAILURE_REDIRECT', value: 'https://${customWebHostname}/auth/failure' }
          ],
          empty(googleClientSecret)   ? [] : [{ name: 'GOOGLE_CLIENT_SECRET',   secretRef: 'google-secret' }],
          empty(applePrivateKey)      ? [] : [{ name: 'APPLE_PRIVATE_KEY',     secretRef: 'apple-key' }],
          empty(facebookClientSecret) ? [] : [{ name: 'FACEBOOK_CLIENT_SECRET', secretRef: 'facebook-secret' }]
        )
      }]
      scale: { minReplicas: 0, maxReplicas: 5 }
    }
  }
  dependsOn: [pgDatabase]
}

// meal-service
resource mealApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-meal'
  location: location
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: '${acr.name}.azurecr.io', username: acr.name, passwordSecretRef: 'acr-password' }]
      secrets: [
        { name: 'acr-password', value: acrPassword }
        { name: 'database-url', value: commonDbUrl }
        { name: 'jwt-secret',   value: jwtSecret }
        { name: 'blob-key',     value: storageKey }
      ]
      ingress: { external: false, targetPort: 8002, transport: 'http' }
    }
    template: {
      containers: [{
        name: 'meal-service'
        image: '${acr.name}.azurecr.io/mealtracker/meal-service:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: [
          { name: 'ENVIRONMENT',     value: 'production' }
          { name: 'DATABASE_URL',    secretRef: 'database-url' }
          { name: 'DB_SCHEMA',       value: 'meal' }
          { name: 'JWT_SECRET',      secretRef: 'jwt-secret' }
          { name: 'BLOB_ACCOUNT_URL', value: blobAccountUrl }
          { name: 'BLOB_ACCOUNT_KEY', secretRef: 'blob-key' }
          { name: 'BLOB_CONTAINER',  value: blobContainerName }
        ]
      }]
      scale: { minReplicas: 0, maxReplicas: 5 }
    }
  }
  dependsOn: [pgDatabase]
}

// nutrition-service
resource nutritionApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-nutrition'
  location: location
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: '${acr.name}.azurecr.io', username: acr.name, passwordSecretRef: 'acr-password' }]
      secrets: [
        { name: 'acr-password', value: acrPassword }
        { name: 'database-url', value: commonDbUrl }
        { name: 'jwt-secret',   value: jwtSecret }
      ]
      ingress: { external: false, targetPort: 8003, transport: 'http' }
    }
    template: {
      containers: [{
        name: 'nutrition-service'
        image: '${acr.name}.azurecr.io/mealtracker/nutrition-service:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: [
          { name: 'ENVIRONMENT',  value: 'production' }
          { name: 'DATABASE_URL', secretRef: 'database-url' }
          { name: 'DB_SCHEMA',    value: 'nutrition' }
          { name: 'JWT_SECRET',   secretRef: 'jwt-secret' }
        ]
      }]
      scale: { minReplicas: 0, maxReplicas: 5 }
    }
  }
  dependsOn: [pgDatabase]
}

// vision-service
resource visionApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-vision'
  location: location
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: '${acr.name}.azurecr.io', username: acr.name, passwordSecretRef: 'acr-password' }]
      secrets: concat(
        [
          { name: 'acr-password', value: acrPassword }
          { name: 'jwt-secret',   value: jwtSecret }
        ],
        empty(runpodApiKey) ? [] : [{ name: 'runpod-key', value: runpodApiKey }]
      )
      ingress: { external: false, targetPort: 8004, transport: 'http' }
    }
    template: {
      containers: [{
        name: 'vision-service'
        image: '${acr.name}.azurecr.io/mealtracker/vision-service:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: concat(
          [
            { name: 'ENVIRONMENT',           value: 'production' }
            { name: 'JWT_SECRET',            secretRef: 'jwt-secret' }
            { name: 'NUTRITION_SERVICE_URL', value: 'https://${namePrefix}-nutrition.internal.${env.properties.defaultDomain}' }
            { name: 'RUNPOD_ENDPOINT_URL',   value: runpodEndpointUrl }
            // If no RunPod endpoint is configured, fall back to stub mode so
            // the rest of the system is exercisable end-to-end.
            { name: 'ALLOW_STUB_MODE',       value: empty(runpodEndpointUrl) ? 'true' : 'false' }
          ],
          empty(runpodApiKey) ? [] : [{ name: 'RUNPOD_API_KEY', secretRef: 'runpod-key' }]
        )
      }]
      scale: { minReplicas: 0, maxReplicas: 3 }
    }
  }
}

// api-gateway — the only one with external ingress
resource gatewayApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-gateway'
  location: location
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: '${acr.name}.azurecr.io', username: acr.name, passwordSecretRef: 'acr-password' }]
      secrets: [
        { name: 'acr-password', value: acrPassword }
        { name: 'jwt-secret',   value: jwtSecret }
      ]
      ingress: {
        external: true
        targetPort: 8080
        transport: 'http'
        allowInsecure: false
      }
    }
    template: {
      containers: [{
        name: 'api-gateway'
        image: '${acr.name}.azurecr.io/mealtracker/api-gateway:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: [
          { name: 'ENVIRONMENT',           value: 'production' }
          { name: 'JWT_SECRET',            secretRef: 'jwt-secret' }
          { name: 'AUTH_SERVICE_URL',      value: 'https://${namePrefix}-auth.internal.${env.properties.defaultDomain}' }
          { name: 'MEAL_SERVICE_URL',      value: 'https://${namePrefix}-meal.internal.${env.properties.defaultDomain}' }
          { name: 'NUTRITION_SERVICE_URL', value: 'https://${namePrefix}-nutrition.internal.${env.properties.defaultDomain}' }
          { name: 'VISION_SERVICE_URL',    value: 'https://${namePrefix}-vision.internal.${env.properties.defaultDomain}' }
          { name: 'CORS_ORIGINS',          value: '["https://${customWebHostname}","https://www.${customWebHostname}"]' }
        ]
      }]
      scale: {
        minReplicas: 1   // keep 1 warm so first call isn't a cold start
        maxReplicas: 10
        rules: [{
          name: 'http-scale'
          http: { metadata: { concurrentRequests: '50' } }
        }]
      }
    }
  }
  dependsOn: [authApp, mealApp, nutritionApp, visionApp]
}

// web-frontend — external, points at the gateway
resource webApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: '${namePrefix}-web'
  location: location
  properties: {
    managedEnvironmentId: env.id
    workloadProfileName: 'Consumption'
    configuration: {
      activeRevisionsMode: 'Single'
      registries: [{ server: '${acr.name}.azurecr.io', username: acr.name, passwordSecretRef: 'acr-password' }]
      secrets: [{ name: 'acr-password', value: acrPassword }]
      ingress: { external: true, targetPort: 3000, transport: 'http', allowInsecure: false }
    }
    template: {
      containers: [{
        name: 'web-frontend'
        image: '${acr.name}.azurecr.io/mealtracker/web-frontend:${imageTag}'
        resources: { cpu: json('0.25'), memory: '0.5Gi' }
        env: [{
          name: 'API_GATEWAY_URL'
          value: 'https://${customApiHostname}'
        }]
      }]
      scale: { minReplicas: 0, maxReplicas: 5 }
    }
  }
}

// ───── Outputs ─────
output gatewayFqdn string = gatewayApp.properties.configuration.ingress.fqdn
output webFqdn     string = webApp.properties.configuration.ingress.fqdn
output acrLoginServer string = acr.properties.loginServer
output postgresHost  string = dbHost
output storageAccountName string = storage.name

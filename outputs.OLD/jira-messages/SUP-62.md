Hi there,

Thanks for reporting this issue with your analytics team's login process. I can see why having to request MFA codes from support for each login would be frustrating.

After investigating, I found that your organization uses single sign-on authentication through an external identity provider. That means your organization controls where authentication codes are routed—not through Salesforce itself, but through your identity management system at the provider level.

Right now, your identity provider is sending MFA codes to your support team instead of directly to analytics@hennessey.com. To fix this, your identity provider admin will need to update that routing configuration on their end.

I'm escalating this to our Engineering team to coordinate with your identity and security teams on making that configuration change. They'll reach out to you with next steps and help coordinate the update process.

Thanks for the context on how this is affecting your team's workflow.

Best regards,
Support

# Re: Meeting Request: Kiro & Bedrock Chatbot Implementation

**From:** Alex Chen <achen@awsexample.com>  
**To:** Marcus <marcus@example.com>  
**Cc:** Dev Team <dev-team@example.com>  
**Date:** February 14, 2026, 9:20 AM  
**Subject:** Re: Meeting Request: Kiro & Bedrock Chatbot Implementation

Hi Marcus,

Great questions! Here's what I'm thinking:

1. **Both** - Kiro can help with infrastructure provisioning (IAM roles, S3 buckets, Bedrock configurations) AND provide AI-assisted guidance for agent design and prompt engineering.

2. We'll use the **fine-tuned Llama 3.1 70B** model that the data science team trained on our customer support conversations. Custom Model Import lets us use this instead of the base Bedrock models.

3. **Specific use case**: I want to explore using Kiro to:
   - Set up Custom Model Import with proper S3 bucket configuration and IAM permissions
   - Configure AgentCore to orchestrate multi-step customer support workflows
   - Integrate tools for: ticket lookup (internal API), knowledge base search (Bedrock KB), and order status checks (DynamoDB)
   - Generate the Lambda functions and API Gateway setup for the chatbot backend

The goal is to reduce manual setup time and let Kiro handle the boilerplate while we focus on the business logic.

See you Tuesday!

Alex

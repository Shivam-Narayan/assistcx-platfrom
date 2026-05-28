aws_s3 = """
# AWS S3 Integration Guide

## Overview

AWS S3 is a highly scalable object storage service designed to store and retrieve any amount of data from anywhere on the web. This integration enables secure file storage, retrieval, and management capabilities within your application. This guide provides detailed instructions for configuring AWS S3 integration, including security best practices and credential management.



## Key Information

- **Integration Name**: AWS S3
- **Auth Type**: APIKey (AWS Access Keys)
- **Base URL**: `https://{bucket-name}.s3.{region}.amazonaws.com`

### Prerequisites

- **AWS Account**: Active AWS account with appropriate permissions
- **IAM Access**: Administrative access to create IAM users and policies
- **S3 Bucket**: Existing S3 bucket or permissions to create new buckets



## Best Practices for Managing AWS Credentials

1. **Use IAM Best Practices**:
   - Create dedicated IAM users for specific applications
   - Follow the principle of least privilege
   - Use IAM roles when possible, especially for EC2 instances
2. **Secure Access Keys**:
   - Store access keys securely using environment variables or AWS Secrets Manager
   - Never commit access keys to version control
   - Rotate access keys regularly (recommended every 90 days)
3. **Monitor Usage**:
   - Enable AWS CloudTrail for API activity monitoring
   - Set up AWS CloudWatch alerts for unusual activity
4. **Bucket Configuration**:
   - Configure appropriate bucket policies
   - Enable versioning for critical data
   - Set up lifecycle policies for cost optimization
5. **Access Logging**:
   - Enable S3 access logging
   - Regularly review access patterns and security settings



## Steps to Obtain AWS S3 Integration Credentials

### Step 1: Create an IAM User

1. **Navigate to IAM**:
   - Log into the AWS Management Console
   - Go to IAM (Identity and Access Management)
2. **Create New User**:
   - Click "Users" > "Add user"
   - Choose a username (e.g., `s3-integration-user`)
   - Select "Access key - Programmatic access"

### Step 2: Configure IAM Permissions

1. **Create Custom Policy**:
   ```json
   {
       "Version": "2012-10-17",
       "Statement": [
           {
               "Effect": "Allow",
               "Action": [
                   "s3:GetObject",
                   "s3:PutObject",
                   "s3:ListBucket",
                   "s3:DeleteObject"
               ],
               "Resource": [
                   "arn:aws:s3:::your-bucket-name/*",
                   "arn:aws:s3:::your-bucket-name"
               ]
           }
       ]
   }
   ```
2. **Attach Policy**:
   - Attach the created policy to your IAM user
   - Review and confirm permissions

### Step 3: Generate Access Keys

1. **Create Access Key**:
   - Select the created user
   - Click "Security credentials" tab
   - Choose "Create access key"
2. **Save Credentials**:
   - **Important**: Copy both the AWS Access Key ID and AWS Secret Access Key
   - Store these securely; the Secret Access Key won't be shown again



## Example Configuration

Here's a sample configuration for AWS S3 integration:

```json
{
    "AWS_ACCESS_KEY_ID": "AKIAIOSFODNN7EXAMPLE",
    "AWS_SECRET_ACCESS_KEY": "wJalrXUtnFEMI/K7MDENG/bPxRfiCYEXAMPLEKEY"
}
```



## Frequently Asked Questions (FAQ)

### 1. What permissions are needed for basic S3 operations?
Basic operations typically require `s3:GetObject`, `s3:PutObject`, `s3:ListBucket`, and `s3:DeleteObject` permissions on your bucket.

### 2. How do I handle large file uploads?
Use multipart uploads for files larger than 100MB. The AWS SDK handles this automatically when configured properly.

### 3. What's the difference between bucket and object permissions?
Bucket permissions control access to the bucket itself, while object permissions control access to individual files within the bucket.



## Troubleshooting Tips

- **Access Denied**: Verify IAM permissions and bucket policies
- **Region Issues**: Ensure the correct region is specified in your configuration
- **Endpoint Errors**: Check if you're using the correct endpoint format for your region
- **Performance Issues**: Consider using AWS Transfer Acceleration for faster uploads/downloads



## Conclusion

Following these guidelines will help you securely integrate AWS S3 into your application. For more detailed information, refer to the [AWS S3 Documentation](https://docs.aws.amazon.com/s3/) and [AWS IAM Best Practices](https://docs.aws.amazon.com/IAM/latest/UserGuide/best-practices.html).
"""
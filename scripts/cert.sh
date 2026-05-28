#!/bin/bash

# Ensure script is run from project root
if [ ! -f "./docker-compose.yml" ]; then
    echo "Please run this script from the project root directory."
    exit 1
fi

# Define paths for environment and certificate files
CERT_DIR="./certs"
ENV_FILE="./.env"

# Attempt to read variables from .env file
if [ -f "$ENV_FILE" ]; then
    export $(grep -v '^#' "$ENV_FILE" | xargs)
else
    echo ".env file not found."
    exit 1
fi

# Check if required variables are set 
if [ -z "$DOMAIN_NAME" ] || [ -z "$WEBAPP_DOMAIN" ] || [ -z "$BACKEND_DOMAIN" ]; then
    echo "DOMAIN_NAME, WEBAPP_DOMAIN, and BACKEND_DOMAIN must be set in .env file."
    exit 1
fi

# Define certificate files
CERT_FILE="$CERT_DIR/$DOMAIN_NAME.pem"
KEY_FILE="$CERT_DIR/$DOMAIN_NAME-key.pem"

check_ports() {
    if lsof -i:80 || lsof -i:443; then
        echo "Ports 80 and/or 443 are in use. Please stop any web servers (like nginx) before running this script."
        exit 1
    fi
}

check_cert_expiry() {
    if [ ! -f "$CERT_FILE" ]; then
        echo "Certificate file not found. Renewal needed."
        return 0
    fi

    DAYS_REMAINING=$(openssl x509 -enddate -noout -in "$CERT_FILE" | cut -d= -f2 | xargs -I{} date -d "{}" +%s)
    NOW=$(date +%s)
    DAYS=$(( ($DAYS_REMAINING - $NOW) / 86400 ))

    if [ $DAYS -lt 30 ]; then
        echo "Certificate expires in $DAYS days. Renewal needed."
        return 0
    else
        echo "Certificate still valid for $DAYS days. No renewal needed."
        return 1
    fi
}

generate_local_cert() {
    if ! command -v mkcert &> /dev/null; then
        echo "mkcert is not installed. Please install mkcert and try again."
        echo "Visit https://github.com/FiloSottile/mkcert for installation instructions."
        exit 1
    fi

    echo "Generating local SSL certificate for subdomains..."
    mkcert -install
    mkcert -cert-file "$CERT_FILE" -key-file "$KEY_FILE" \
        "$WEBAPP_DOMAIN" \
        "$BACKEND_DOMAIN"

    if [ $? -ne 0 ]; then
        echo "Local certificate generation failed."
        exit 1
    fi

    echo "Local certificates successfully generated."
}

generate_letsencrypt_cert() {
    if ! command -v certbot &> /dev/null; then
        echo "Certbot is not installed. Please install Certbot and try again."
        echo "You can install it using: sudo apt-get update && sudo apt-get install -y certbot"
        exit 1
    fi

    check_ports

    echo "Generating Let's Encrypt SSL certificate for subdomains..."
    
    sudo certbot certonly --standalone \
        -d "$WEBAPP_DOMAIN" \
        -d "$BACKEND_DOMAIN" \
        --non-interactive \
        --agree-tos \
        --email zenstackai@gmail.com \
        --expand

    if [ $? -ne 0 ]; then
        echo "Let's Encrypt certificate generation failed."
        exit 1
    fi

    echo "Copying Let's Encrypt certificates..."
    # Using WEBAPP_DOMAIN as the primary domain (certbot uses this as directory name)
    if ! sudo cp "/etc/letsencrypt/live/$WEBAPP_DOMAIN/fullchain.pem" "$CERT_FILE" || \
       ! sudo cp "/etc/letsencrypt/live/$WEBAPP_DOMAIN/privkey.pem" "$KEY_FILE"; then
        echo "Failed to copy certificates. Please check permissions and paths."
        exit 1
    fi
    
    sudo chown $(whoami):$(whoami) "$CERT_FILE" "$KEY_FILE"
    sudo chmod 644 "$CERT_FILE" "$KEY_FILE"

    echo "Let's Encrypt certificates successfully generated and copied."
}

renew_certificates() {
    echo "Checking certificate expiry..."
    
    if check_cert_expiry; then
        echo "Stopping nginx container..."
        docker compose stop nginx
        
        echo "Renewing certificates..."
        if ! generate_letsencrypt_cert; then
            echo "Certificate renewal failed! Restarting nginx with existing certificates..."
            docker compose start nginx
            echo "Certificate renewal failed at $(date)" >> /var/log/cert-renewal.log
            exit 1
        fi
        
        echo "Starting nginx container..."
        docker compose start nginx
        
        # Verify nginx started successfully
        if ! docker compose ps nginx | grep -q "running"; then
            echo "Failed to restart nginx! Check the configuration."
            echo "Nginx failed to restart after renewal at $(date)" >> /var/log/cert-renewal.log
            exit 1
        fi
        
        echo "Certificate renewal complete at $(date)" >> /var/log/cert-renewal.log
    else
        echo "Certificate renewal skipped at $(date)" >> /var/log/cert-renewal.log
    fi
}

# Parse arguments
LOCAL=false
RENEW=false

for arg in "$@"; do
    case "$arg" in
        "--local")
            LOCAL=true
            ;;
        "--renew")
            RENEW=true
            ;;
        *)
            echo "Unknown argument: $arg"
            echo "Usage: $0 [--local] [--renew]"
            exit 1
            ;;
    esac
done

# Main execution
mkdir -p "$CERT_DIR"

if $LOCAL && $RENEW; then
    echo "Error: Cannot use --local and --renew together"
    exit 1
elif $LOCAL; then
    generate_local_cert
elif $RENEW; then
    renew_certificates
else
    generate_letsencrypt_cert
fi

echo "Certificate setup complete."
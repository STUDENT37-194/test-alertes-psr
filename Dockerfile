# Image Windows avec Python installé
FROM mcr.microsoft.com/windows/servercore:ltsc2022

# Installer Chocolatey pour installer Python
RUN powershell -NoProfile -ExecutionPolicy Bypass \
    iex ((New-Object System.Net.WebClient).DownloadString('https://chocolatey.org/install.ps1'))

# Installer Python 3.11
RUN choco install python --version=3.11 -y

# Ajouter Python au PATH
ENV PATH="C:\\Python311;C:\\Python311\\Scripts;${PATH}"

# Installer pip packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copier ton script
WORKDIR /app
COPY . /app

# Commande de lancement
CMD ["python", "ton_script.py"]

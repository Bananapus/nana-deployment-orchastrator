import subprocess
import os
import json
import time
import requests
import subprocess
import shutil

# Special deployments
bannyverse_repos = ["mejango/bannyverse-core"]
fee_project_repos = ["Bananapus/fee-project-deployer"]

# Most peripheral -> Most Core repos, will be executed bottom up.
revnet_repos = ["rev-net/revnet-core"]
croptop_repos = ["xBA5ED/croptop-core"]
croptop_repos.extend(revnet_repos)

nana_suckers_repos = ["Bananapus/nana-suckers"]
nana_suckers_repos.extend(croptop_repos)

nana_721_repos = ["Bananapus/nana-721-hook"]
nana_721_repos.extend(croptop_repos)

nana_core_repos = ["Bananapus/nana-core", "Bananapus/nana-721-hook"]
nana_core_repos.extend(nana_suckers_repos)

# Define options and associated repositories
options = {
    "nana-core": nana_core_repos,
    "nana-721": nana_721_repos,
    "nana-suckers": nana_suckers_repos,
    "croptop-core": croptop_repos,
    "revnet-core" : revnet_repos,

    "special: create fee project (nana)": bannyverse_repos,
    "special: create bannyverse project": fee_project_repos,
}

# Function to run shell commands
def run_command(command, cwd=None, debug=False):
    if debug:
        print(f"DEBUG: Would run command: {' '.join(command)} in {cwd}")
        return 0
    else:
        result = subprocess.run(command, cwd=cwd, text=True, capture_output=True)
        # print(result.stdout)
        if result.returncode != 0:
            print("Error:", result.stderr)
        return result.returncode

# Update package.json with a new version
def update_package_json(repo_path, new_version, debug=False):
    with open(os.path.join(repo_path, "package.json"), "r+") as file:
        data = json.load(file)
        data["version"] = new_version
        file.seek(0)
        json.dump(data, file, indent=4)
        file.truncate()
    if not debug:
        print(f"Updated package.json with version {new_version}")

def wait_for_deployment():
    print("Press Enter when the deployment is done...")
    time.sleep(5)
    input("")

def fetch_and_check_artifacts(repo_path):
    # Fetch the deployment artifacts
    print("Fetching artifacts...")
    run_command(["npm", "run", "artifacts"], cwd=repo_path)

    # Define the directory to check for changes
    directory_to_check = "deployments/"

    # Run the git status command with --porcelain option
    result = subprocess.run(["git", "status", "--porcelain", directory_to_check],
                            stdout=subprocess.PIPE, 
                            text=True,
                            cwd=repo_path)

    # Check if the output is empty
    if not result.stdout.strip():
        print("No change in deployment artifacts...")
        print("Options")
        print("r - Retry fetching artifacts")
        print("c - Continue without fetching artifacts (aka this was expected)")
        print("e - Exit")

        choice = input("What do you wish to do (r/C/e): ").strip().lower()
        if choice == 'c' or choice == '':
            print("Continueing...")
            return False

        if choice == 'r':
            print("Retrying...")
            return fetch_and_check_artifacts(repo_path)
        
        print("Exiting...")
        exit(1)
    
    return True

# Ask for user input
use_http = input("Use SSH for git repositories? (YES/no): ").strip().lower() == "no"
protocol_prefix = "git@github.com:" if not use_http else "https://github.com/"

# Pick an item from the list
print("Please select an option:")
for i, option in enumerate(options, start=1):
    print(f"{i}. {option}")
selection = int(input("Enter the number of your choice: ")) - 1
selected_option = list(options.keys())[selection]

# Enable debug/test mode
# debug_mode = input("Enable debug mode ()? (yes/NO): ").strip().lower() == "yes"

# Create a temporary directory for the repositories
temp_dir = "temp_repos"
os.makedirs(temp_dir, exist_ok=True)

for repo in options[selected_option]:
    repo_url = protocol_prefix + repo
    repo_name = repo.split("/")[-1]
    repo_path = os.path.join(temp_dir, repo_name)

    # Clone and setup each repository
    print(f"Cloning {repo_url}...")
    run_command(["git", "clone", repo_url], cwd=temp_dir)

    # TODO: remove
    run_command(["git", "checkout", "feat/sphinx"], cwd=repo_path)

    print("Installing and updating npm packages, this may take a while...")
    run_command(["npm", "i"], cwd=repo_path)
    # run_command(["npm", "update"], cwd=repo_path)

    # Copy .env file
    shutil.copyfile('./.env', repo_path + '/.env')

    print("Updating to latest version of sphinx...")
    run_command(["npx", "sphinx", "install"], cwd=repo_path)

    # Check if the 'cache' folder exists
    if not os.path.exists(repo_path + "/cache"):
        # If it doesn't exist, create it
        os.makedirs(repo_path + "/cache")
        print(f"Created 'cache' folder.")

    # Run the deployment in a new window
    print("Starting Sphinx deployment process in a new window...")
    result = subprocess.run(['alacritty',  '-e', "npm", "run", "deploy:testnets"], cwd=repo_path)

    if result.returncode != 0:
        print("Deployment failed or cancelled...")
        exit(1);
    
    # wait until the deployment has completed
    wait_for_deployment() 

    # Check if there was anything deployed, if there wasn't we continue to the next deployment.
    if not fetch_and_check_artifacts(repo_path): 
        continue

    # Show current version and ask for new version
    package_json_path = os.path.join(repo_path, "package.json")
    with open(package_json_path, "r") as file:
        current_version = json.load(file)["version"]
    print(f"Current version of {repo_name} is {current_version}.")
    new_version = input("What should the new version number be? ")

    update_package_json(repo_path, new_version)

    print("What do you wish to do:")
    print("n - Commit & Push changes to the remote, then perform next deployment")
    print("c - Commit & Push changes to the remote, but do not continue to next deployment")
    print("e - Exit without commiting")
    choice = input("Remove the temporary directory? (N/c/e): ").strip().lower()

    if choice == 'e':
        exit(1)

    # Add the artifacts and bump the package version.
    run_command(["git", "add", "package.json",], cwd=repo_path)
    run_command(["git", "add", "deployment/*"], cwd=repo_path)

    # Commit the changes and push them.
    run_command(["git", "commit", "-m", "ci: bump version and deployment"], cwd=repo_path)
    run_command(["git", "push"], cwd=repo_path)

    # We have commited, we now exit before the next deployment.
    if choice == 'c':
        exit(1)
    
    time.sleep(5)

# Cleanup
if input("Remove the temporary directory? (yes/no): ").strip().lower() == "yes":
    for root, dirs, files in os.walk(temp_dir, topdown=False):
        for name in files:
            os.remove(os.path.join(root, name))
        for name in dirs:
            os.rmdir(os.path.join(root, name))
    os.rmdir(temp_dir)
    print("Temporary directory removed.")

import sys
import json

def update_task_definition(input_file, new_tag, output_file):
    """
    Update the image tag in the task definition and save to a new file.

    :param input_file: Path to the file containing the task definition JSON.
    :param new_tag: New tag to update the image with.
    :param output_file: Path to the file where the updated task definition will be saved.
    """
    
    print(f"Updating task definition from {input_file} with new tag {new_tag} and saving to {output_file}")
    
    try:
        with open(input_file, 'r') as file:
            task_def = json.load(file)["taskDefinition"]

        # Extract and update the container definition
        for container_def in task_def["containerDefinitions"]:
            if "image" in container_def:
                image = container_def["image"]
                base_image, _ = image.split(":")
                new_image = f"{base_image}:{new_tag}"
                container_def["image"] = new_image
            
            environment = container_def.get("environment", [])
            executed = False
            for env_var in environment:
                if env_var["name"] == "VERSION":
                    executed = True
                    env_var["value"] = new_tag
            if not executed:
                version = {"name": "VERSION", "value": new_tag}
                environment.append(version)

        # Remove fields not allowed in register-task-definition
        task_def.pop("status", None)
        task_def.pop("revision", None)
        task_def.pop("taskDefinitionArn", None)
        task_def.pop("requiresAttributes", None)
        task_def.pop("compatibilities", None)
        task_def.pop("registeredAt", None)
        task_def.pop("registeredBy", None)

        with open(output_file, 'w') as file:
            json.dump(task_def, file, indent=4)

        print(f"Updated task definition saved to {output_file}")
        
    except FileNotFoundError:
        print(f"File not found: {input_file}")
        sys.exit(1)
    except json.JSONDecodeError:
        print("Invalid JSON input.")
        sys.exit(1)
    except KeyError:
        print("Invalid task definition structure.")
        sys.exit(1)

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python update_task_def.py <input_file> <new_tag> <output_file>")
        sys.exit(1)

    argv = sys.argv
    update_task_definition(argv[1], argv[2], argv[3])

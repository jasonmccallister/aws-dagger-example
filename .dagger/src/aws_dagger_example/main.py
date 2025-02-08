import base64
import boto3
from dagger import dag, function, object_type, Doc, DefaultPath, Service, Directory, Container, Platform, Secret
from typing import Annotated


@object_type
class AwsDaggerExample:
    image: Annotated[str, Doc("The base image to use for building the container")] = "python:3-slim"

    dir: Annotated[Directory, Doc("The directory containing the source code"), DefaultPath(".")]

    @function
    def build(self) -> Container:
        """Build the application"""
        return (
            dag.container(platform=Platform("linux/amd64"))
            .from_(self.image)
            .with_workdir("/app")
            .with_mounted_directory("/app", self.dir)
            .with_exec(["pip", "install", "uv"])
            .with_exec(["uv", "venv"])
            .with_exec(["uv", "pip", "install", "-r", "requirements.txt", "--system"])
            .with_exposed_port(3000)
        )

    @function
    def run(self) -> Service:
        """Run the application"""
        return (
            self.build()
            .with_mounted_directory("/app", self.dir)
            .as_service(args=["python3", "app.py"])
        )

    @function
    def test(self) -> str:
        """Run the application tests"""
        return (
            self.build()
            .with_mounted_directory("/app", self.dir)
            .with_exec(["pytest", "tests"])
            .stdout()
        )

    @function
    async def push(
        self,
        access_key: Annotated[Secret, Doc("The AWS access key for deploying the application")],
        secret_key: Annotated[Secret, Doc("The AWS secret key for deploying the application")],
        session_token: Annotated[Secret, Doc("The AWS session token for deploying the application")],
        region: Annotated[str, Doc("The region for the application")],
        registry: Annotated[str, Doc("The registry to use for pushing the container image")],
    ) -> str:
        """Push the image to ECR"""
        ecr_client = boto3.client("ecr",
            aws_access_key_id=await access_key.plaintext(),
            aws_secret_access_key=await secret_key.plaintext(),
            aws_session_token=await session_token.plaintext(),
            region_name=region,
        )

        response = ecr_client.get_authorization_token()

        if not response["authorizationData"]:
            raise ValueError("No authorization data found")

        auth_data = response["authorizationData"][0]
        token = auth_data["authorizationToken"]
        registry_url = auth_data["proxyEndpoint"]

        decoded_token = base64.b64decode(token).decode("utf-8")
        username, password = decoded_token.split(":")
        auth_password = dag.set_secret("password", password)

        return await self.build().with_registry_auth(registry_url, username, auth_password).publish(registry)


    @function
    async def deploy(
        self,
        cluster: Annotated[str, Doc("The name of the cluster for the application")],
        access_key: Annotated[Secret, Doc("The AWS access key for deploying the application")],
        secret_key: Annotated[Secret, Doc("The AWS secret key for deploying the application")],
        session_token: Annotated[Secret, Doc("The AWS session token for deploying the application")],
        region: Annotated[str, Doc("The region for the application")],
        service: Annotated[str, Doc("The ECS Service to update")],
        task_definition_family: Annotated[str, Doc("The Task Defintion name to update")],
        registry: Annotated[str, Doc("The registry to use for pushing the container image")],
    ) -> str:
        """Deploy the application to ECS"""
        image = await self.push(access_key, secret_key, session_token, region, registry)

        ecs_client = boto3.client(
            'ecs',
            aws_access_key_id=await access_key.plaintext(),
            aws_secret_access_key=await secret_key.plaintext(),
            aws_session_token=await session_token.plaintext(),
            region_name=region
        )

        try:
            # Retrieve the most recent revision of the task definition family
            response = ecs_client.list_task_definitions(
                familyPrefix=task_definition_family,
                sort='DESC',
                maxResults=1
            )

            if not response['taskDefinitionArns']:
                raise ValueError(f"No task definitions found for family: {task_definition_family}")

            # Get the most recent task definition ARN
            latest_task_definition_arn = response['taskDefinitionArns'][0]

            print(f"Latest task definition ARN: {latest_task_definition_arn}")

            # describe the task definition
            task_definition = ecs_client.describe_task_definition(
                taskDefinition=latest_task_definition_arn
            )['taskDefinition']

            # Update the container image with the provided SHA
            for ctr in task_definition['containerDefinitions']:
                if 'image' in ctr:
                    ctr['image'] = image


            # Register the new task definition
            new_task_definition = ecs_client.register_task_definition(
                family=task_definition['family'],
                containerDefinitions=task_definition['containerDefinitions'],
                volumes=task_definition.get('volumes', []),
                taskRoleArn=task_definition.get('taskRoleArn'),
                executionRoleArn=task_definition.get('executionRoleArn'),
                networkMode=task_definition.get('networkMode'),
                requiresCompatibilities=task_definition.get('requiresCompatibilities', []),
                cpu=task_definition.get('cpu'),
                memory=task_definition.get('memory')
            )

            new_task_definition_arn = new_task_definition['taskDefinition']['taskDefinitionArn']

            # deregister the old task definition as not in use
            ecs_client.deregister_task_definition(
                taskDefinition=latest_task_definition_arn
            )

            # update the service
            ecs_client.update_service(
                cluster=cluster,
                service=service,
                taskDefinition=new_task_definition_arn
            )

            return f"Service {service} updated to use task definition {new_task_definition_arn}"

        except Exception as e:
            print(f"Error updating ECS service: {e}")
            raise

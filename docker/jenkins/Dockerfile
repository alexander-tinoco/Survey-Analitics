# Jenkins with a Docker client and the plugins a Jenkinsfile build needs.
#
# The base version is pinned rather than tracking :lts, so a rebuild produces
# the same server. It has to stay recent enough for the plugins below: they
# refuse to install on an older core, which is how this pin gets bumped.
#
# The official image ships no docker binary, so mounting the host socket into
# it is not enough on its own: every stage of the pipeline shells out to
# `docker compose`, and without the client they all fail with
# "docker: command not found".
FROM jenkins/jenkins:2.516.3-jdk21

USER root

# The CLI and the compose plugin only — not the daemon. The daemon comes from
# the host through the mounted socket.
RUN apt-get update \
    && apt-get install --no-install-recommends -y ca-certificates curl gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && chmod a+r /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/debian $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
        > /etc/apt/sources.list.d/docker.list \
    && apt-get update \
    && apt-get install --no-install-recommends -y docker-ce-cli docker-compose-plugin \
    && rm -rf /var/lib/apt/lists/*

# The setup wizard is disabled, which also means none of the suggested plugins
# are installed. These are the ones a Jenkinsfile-driven build actually needs:
# the pipeline engine, Git for checkout, and the workspace cleaner the
# post-build step calls.
COPY docker/jenkins/plugins.txt /usr/share/jenkins/ref/plugins.txt
RUN jenkins-plugin-cli --plugin-file /usr/share/jenkins/ref/plugins.txt

# The mounted workspace belongs to the host user, not to anyone inside this
# container, and git refuses to operate on a repository it considers to have
# "dubious ownership". That check stops a repository someone else controls
# from running its hooks against you; here the repository is the developer's
# own and the mount is read-only, so it is declared safe.
#
# Written into both home directories rather than /etc/gitconfig: Jenkins
# spawns git without inheriting the container's environment, and the process
# that serves a local clone picked up neither the system file nor
# GIT_CONFIG_* variables. The per-user config is the one it reads.
RUN git config --global --add safe.directory "*" \
    && HOME=/var/jenkins_home git config --global --add safe.directory "*" \
    && chown jenkins:jenkins /var/jenkins_home/.gitconfig

USER jenkins

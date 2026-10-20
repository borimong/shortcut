FROM maven:3.9-eclipse-temurin-21 AS build
WORKDIR /src
# 소스만 바뀐 재빌드에서 의존성 내려받기 계층을 다시 쓰려고 pom.xml을 먼저 복사한다.
COPY pom.xml .
RUN mvn -q -B dependency:go-offline
COPY src ./src
RUN mvn -q -B -DskipTests package

FROM eclipse-temurin:21-jre
WORKDIR /app
COPY --from=build /src/target/shortcut-backend.jar app.jar
EXPOSE 8080
# api와 worker가 같은 이미지를 쓰고 SPRING_PROFILES_ACTIVE로 역할을 고른다.
ENTRYPOINT ["java", "-jar", "/app/app.jar"]

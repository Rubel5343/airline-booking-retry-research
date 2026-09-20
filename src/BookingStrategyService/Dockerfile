FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props ./
COPY src/BookingStrategyService/BookingStrategyService.csproj src/BookingStrategyService/
RUN dotnet restore src/BookingStrategyService/BookingStrategyService.csproj
COPY src/BookingStrategyService/ src/BookingStrategyService/
RUN dotnet publish src/BookingStrategyService/BookingStrategyService.csproj -c Release -o /app/publish --no-restore

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "BookingStrategyService.dll"]

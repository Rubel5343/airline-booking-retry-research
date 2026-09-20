FROM mcr.microsoft.com/dotnet/sdk:10.0 AS build
WORKDIR /src
COPY Directory.Build.props ./
COPY src/SupplierSimulator/SupplierSimulator.csproj src/SupplierSimulator/
RUN dotnet restore src/SupplierSimulator/SupplierSimulator.csproj
COPY src/SupplierSimulator/ src/SupplierSimulator/
RUN dotnet publish src/SupplierSimulator/SupplierSimulator.csproj -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:10.0
WORKDIR /app
COPY --from=build /app/publish .
ENTRYPOINT ["dotnet", "SupplierSimulator.dll"]

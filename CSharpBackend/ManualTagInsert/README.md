# Manual Tag Insert Utility

Small .NET console app that upserts a tag mapping directly into `historian_meta.tag_master` using the same rules as the web API. It reads the connection string from the root `appsettings.json`, so no extra config is needed.

## Usage

From the repository root:

```cmd
cd ManualTagInsert
dotnet run -- --tagId=MANUAL_TAG_DEMO --tagName="Manual Tag" --dataType=double --interval=2000 --plant=Plant1 --area=Area1 --equipment=Equipment1
```

Arguments are optional and default to sensible values (`tagId=MANUAL_TAG_DEMO`, `interval=1000`, plant/area/equipment set to `Plant1/Area1/Equipment1`). The tool prints both the upsert result and the persisted row so you can confirm the database commit without running the full web server.

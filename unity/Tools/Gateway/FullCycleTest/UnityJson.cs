namespace UnityEngine
{
    // Standalone contract checks; the Unity Editor also runs these against its actual JsonUtility.
    public static class JsonUtility
    {
        static readonly System.Text.Json.JsonSerializerOptions options=new(){IncludeFields=true};
        public static T FromJson<T>(string value)=>System.Text.Json.JsonSerializer.Deserialize<T>(value,options);
        public static string ToJson(object value)=>System.Text.Json.JsonSerializer.Serialize(value,value.GetType(),options);
    }
}

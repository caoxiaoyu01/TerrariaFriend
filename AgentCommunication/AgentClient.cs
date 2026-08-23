#nullable enable

using System;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using TerrariaFriend.Triggering;

namespace TerrariaFriend.AgentCommunication
{
	// 只负责 TriggerEvent 与 FastAPI 之间的 HTTP JSON 通信
	public sealed class AgentClient
	{
		private static readonly HttpClient HttpClient = new HttpClient
		{
			Timeout = AgentConfiguration.RequestTimeout
		};

		private static readonly JsonSerializerOptions JsonOptions = new JsonSerializerOptions
		{
			PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
			PropertyNameCaseInsensitive = true,
			DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
			Converters = { new JsonStringEnumConverter() }
		};

		public async Task<AgentResponse> SendTriggerAsync(
			TriggerEvent trigger,
			CancellationToken cancellationToken = default)
		{
			try
			{
				// 将 TriggerEvent 序列化为 FastAPI 接收的 JSON
				string json = JsonSerializer.Serialize(trigger, JsonOptions);

				using StringContent content = new StringContent(json, Encoding.UTF8, "application/json");

				// 异步发送请求且不切回游戏线程上下文
				using HttpResponseMessage response = await HttpClient.PostAsync(
					AgentConfiguration.TriggerEndpoint,
					content,
					cancellationToken).ConfigureAwait(false);

				// 非成功状态码直接进入网络异常处理
				response.EnsureSuccessStatusCode();
				string responseJson = await response.Content.ReadAsStringAsync(cancellationToken)
					.ConfigureAwait(false);

				// 将 FastAPI 响应转换为 C# DTO
				return JsonSerializer.Deserialize<AgentResponse>(responseJson, JsonOptions)
					?? Failed("Agent returned an empty response.");
			}
			// 兜底
			catch (OperationCanceledException) when (!cancellationToken.IsCancellationRequested)
			{
				return Failed("Agent request timed out.");
			}
			catch (OperationCanceledException)
			{
				return Failed("Agent request was cancelled.");
			}
			catch (HttpRequestException exception)
			{
				return Failed($"Agent network error: {exception.Message}");
			}
			catch (JsonException exception)
			{
				return Failed($"Invalid Agent response JSON: {exception.Message}");
			}
		}

		private static AgentResponse Failed(string error)
		{
			return new AgentResponse("ERROR", null, null, false, error);
		}
	}
}

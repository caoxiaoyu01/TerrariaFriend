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
	// 负责把游戏事件发给智能体服务并接收回复
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
				// 把游戏事件转换成服务端能读取的数据
				string json = JsonSerializer.Serialize(trigger, JsonOptions);

				using StringContent content = new StringContent(json, Encoding.UTF8, "application/json");

				// 在后台发送请求 不占用游戏线程
				using HttpResponseMessage response = await HttpClient.PostAsync(
					AgentConfiguration.TriggerEndpoint,
					content,
					cancellationToken).ConfigureAwait(false);

				// 服务端返回错误状态时按网络错误处理
				response.EnsureSuccessStatusCode();
				string responseJson = await response.Content.ReadAsStringAsync(cancellationToken)
					.ConfigureAwait(false);

				// 把服务端回复转换成游戏端对象
				return JsonSerializer.Deserialize<AgentResponse>(responseJson, JsonOptions)
					?? Failed("Agent returned an empty response.");
			}
			// 网络或数据解析失败时统一返回错误
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

		public async Task SendWorldSessionEndedAsync(
			DateTimeOffset occurredAt,
			CancellationToken cancellationToken = default)
		{
			string json = JsonSerializer.Serialize(
				new { occurredAt },
				JsonOptions);
			using StringContent content = new StringContent(json, Encoding.UTF8, "application/json");
			using HttpResponseMessage response = await HttpClient.PostAsync(
				AgentConfiguration.WorldSessionEndedEndpoint,
				content,
				cancellationToken).ConfigureAwait(false);
			response.EnsureSuccessStatusCode();
		}

		private static AgentResponse Failed(string error)
		{
			return new AgentResponse("ERROR", null, null, false, error);
		}
	}
}
